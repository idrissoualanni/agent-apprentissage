"""Abstraction de base de donnees — SQLite (dev/tests) ou PostgreSQL (Neon, prod).

Selection automatique : si DATABASE_URL est definie dans l'environnement,
PostgreSQL est utilise ; sinon SQLite.

Les requetes ecrites en dialecte SQLite (? placeholder, datetime('now')) sont
adaptees a la volee pour Postgres (%s placeholder, NOW()).
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


def is_postgres() -> bool:
    """True si une URL Postgres (Neon) est configuree."""
    return bool(os.getenv("DATABASE_URL"))


_pg_pool = None
_pg_pool_failed = False


def _get_pg_pool():
    """Pool de connexions Postgres paresseux (singleton par processus).

    Retourne None si le pool ne peut pas etre cree (fallback sur une
    connexion directe a chaque appel).
    """
    global _pg_pool, _pg_pool_failed
    if _pg_pool is not None or _pg_pool_failed:
        return _pg_pool
    try:
        from psycopg2 import pool as _pool
        _pg_pool = _pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=8,
            dsn=os.getenv("DATABASE_URL"),
            connect_timeout=10,
        )
        logger.info("Pool de connexions Postgres initialise (1-8)")
    except Exception as e:
        _pg_pool_failed = True
        logger.warning(f"Pool Postgres indisponible, fallback connexion directe: {e}")
    return _pg_pool


def _adapt_sql_for_postgres(sql: str) -> str:
    """Adapte une requete SQL SQLite pour PostgreSQL."""
    # datetime('now') -> NOW()
    sql = re.sub(r"datetime\(\s*'now'\s*\)", "NOW()", sql, flags=re.IGNORECASE)
    # datetime('now', '-N days') -> NOW() - INTERVAL 'N days'
    sql = re.sub(
        r"datetime\(\s*'now'\s*,\s*'(-?\d+)\s+days'\s*\)",
        lambda m: f"NOW() - INTERVAL '{abs(int(m.group(1)))} days'"
        if int(m.group(1)) < 0 else f"NOW() + INTERVAL '{int(m.group(1))} days'",
        sql,
        flags=re.IGNORECASE,
    )
    # Placeholder ? -> %s (hors chaines de caracteres)
    sql = _replace_placeholders(sql)
    return sql


def _replace_placeholders(sql: str) -> str:
    """Remplace les placeholders ? par %s, en ignorant ceux dans les chaines."""
    result = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            # Gere les quotes echappees ''
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                result.append("''")
                i += 2
                continue
            in_single = not in_single
            result.append(ch)
        elif ch == "?" and not in_single:
            result.append("%s")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


class _PostgresCursorAdapter:
    """Adapte un curseur psycopg2 pour accepter des requetes dialecte SQLite."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        sql = _adapt_sql_for_postgres(sql)
        self._last_was_insert = sql.lstrip().upper().startswith("INSERT")
        if params is not None:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def executemany(self, sql, seq_params):
        sql = _adapt_sql_for_postgres(sql)
        self._cursor.executemany(sql, seq_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        # psycopg2 ne fournit pas lastrowid comme SQLite : on utilise
        # lastval() qui retourne le dernier id genere par une sequence
        # (SERIAL) dans la transaction courante.
        if not getattr(self, "_last_was_insert", False):
            return None
        try:
            self._cursor.execute("SAVEPOINT dsh_lastrowid")
            self._cursor.execute("SELECT lastval()")
            row = self._cursor.fetchone()
            self._cursor.execute("RELEASE SAVEPOINT dsh_lastrowid")
            if row is None:
                return None
            if isinstance(row, dict):
                return next(iter(row.values()))
            return row[0]
        except Exception:
            try:
                self._cursor.execute("ROLLBACK TO SAVEPOINT dsh_lastrowid")
            except Exception:
                pass
            return None

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PostgresConnAdapter:
    """Adapte une connexion psycopg2 a l'interface sqlite3.Connection."""

    def __init__(self, conn, cursor_factory=None):
        self._conn = conn
        self._cursor_factory = cursor_factory

    def _new_cursor(self):
        if self._cursor_factory is not None:
            return self._conn.cursor(cursor_factory=self._cursor_factory)
        return self._conn.cursor()

    def execute(self, sql, params=None):
        cursor = self._new_cursor()
        adapter = _PostgresCursorAdapter(cursor)
        adapter.execute(sql, params)
        return adapter

    def executemany(self, sql, seq_params):
        cursor = self._new_cursor()
        adapter = _PostgresCursorAdapter(cursor)
        adapter.executemany(sql, seq_params)
        return adapter

    def cursor(self):
        return _PostgresCursorAdapter(self._new_cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def get_db_connection(db_path: Optional[Path] = None):
    """Context manager retournant une connexion (SQLite ou Postgres).

    Compatible avec l'ancien get_connection de crud.py : yield une connexion
    avec commit/rollback automatique.

    Postgres : utilise un pool de connexions (ThreadedConnectionPool) pour
    eviter de payer l'etablissement TCP+TLS a chaque requete (~1s depuis
    l'Europe vers Neon us-east-2).
    """
    if is_postgres():
        import psycopg2
        import psycopg2.extras
        pool = _get_pg_pool()
        if pool is not None:
            conn = pool.getconn()
            from_pool = True
        else:
            conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            from_pool = False
        conn.autocommit = False
        # RealDictCursor : acces par nom de colonne (equivalent sqlite3.Row).
        adapter = _PostgresConnAdapter(conn, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield adapter
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if from_pool:
                # rollback de securite avant remise au pool (pgbouncer
                # transactionnel : la connexion doit revenir propre).
                try:
                    conn.rollback()
                except Exception:
                    pass
                pool.putconn(conn)
            else:
                conn.close()
    else:
        from apps.api.config import DB_PATH
        path = db_path or DB_PATH
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
