import sqlite3
import tempfile
from pathlib import Path

import pytest

from apps.api.db import migrations


@pytest.fixture
def tmp_db():
    """DB SQLite temporaire avec le schema V3 complet + migrations appliquees."""
    path = Path(tempfile.mkdtemp()) / "test.db"
    conn = sqlite3.connect(str(path))
    schema = Path("apps/api/db/schema_v3.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
    conn.close()
    migrations.run_migrations(path)
    yield path


@pytest.fixture
def mock_retriever():
    """Retriever factice qui ne retourne aucun document (pas de RAG reel)."""

    class _R:
        def invoke(self, q):
            return []

    return _R()
