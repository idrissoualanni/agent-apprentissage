"""Registre des connexions WebSocket actives — une connexion par session.

Si une deuxieme connexion arrive pour la meme session (2 onglets),
la plus recente remplace l'ancienne (close code 4000). Spec §6.

Note heartbeat : le ping client→serveur (25s) + le nettoyage automatique
lors d'un send echoue suffisent a detecter les connexions mortes pour
cette app mono-utilisateur (deviation documentee du spec §3.1).
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[int, object] = {}
        self._busy: set = set()

    async def connect(self, session_id: int, websocket) -> None:
        old = self._connections.get(session_id)
        if old is not None:
            try:
                await old.close(code=4000, reason="replaced_by_new_connection")
            except Exception:
                pass
        self._connections[session_id] = websocket
        logger.info(f"WS connecte: session={session_id}")

    def disconnect(self, session_id: int, websocket) -> None:
        if self._connections.get(session_id) is websocket:
            self._connections.pop(session_id, None)
            logger.info(f"WS deconnecte: session={session_id}")
        self._busy.discard(session_id)

    async def send(self, session_id: int, payload: dict) -> bool:
        ws = self._connections.get(session_id)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self._connections.pop(session_id, None)
            return False

    def is_busy(self, session_id: int) -> bool:
        return session_id in self._busy

    def set_busy(self, session_id: int, busy: bool) -> None:
        if busy:
            self._busy.add(session_id)
        else:
            self._busy.discard(session_id)


manager = ConnectionManager()
