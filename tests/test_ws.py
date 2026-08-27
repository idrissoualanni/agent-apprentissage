"""Tests du protocole WebSocket, du ConnectionManager et du router /ws."""
import asyncio
import time

import pytest
from cachetools import TTLCache  # noqa: F401 (garde l'import rapide)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# ─── Protocole ────────────────────────────────────────────────────────────


def test_protocol_builders():
    from apps.api.ws import protocol as p
    assert p.token_msg("bon") == {"type": "token", "text": "bon"}
    assert p.pong_msg() == {"type": "pong"}
    assert p.error_msg("agent_busy") == {"type": "error", "message": "agent_busy"}
    conf = p.confirmation_request_msg("competency_creation", "Veux-tu créer X ?")
    assert conf["type"] == "confirmation_request"
    assert conf["confirmation_type"] == "competency_creation"
    assert conf["confirmation_prompt"] == "Veux-tu créer X ?"
    notif = p.notification_msg("revision_due", {"count": 3})
    assert notif == {"type": "notification", "kind": "revision_due",
                     "data": {"count": 3}}
    msg = p.final_message_msg({
        "answer": "réponse", "method": "scaffold", "thread_id": "t1",
        "artifacts": [], "tool_transparency": [],
    })
    assert msg["type"] == "message"
    assert msg["answer"] == "réponse"


# ─── ConnectionManager ────────────────────────────────────────────────────


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = None

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


def test_manager_connect_send_disconnect():
    from apps.api.ws.manager import ConnectionManager

    async def run():
        m = ConnectionManager()
        ws = FakeWebSocket()
        await m.connect(1, ws)
        ok = await m.send(1, {"type": "pong"})
        assert ok and ws.sent == [{"type": "pong"}]
        m.disconnect(1, ws)
        assert await m.send(1, {"x": 1}) is False

    asyncio.run(run())


def test_manager_replace_connection():
    from apps.api.ws.manager import ConnectionManager

    async def run():
        m = ConnectionManager()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await m.connect(7, ws1)
        await m.connect(7, ws2)  # 2e onglet : remplace la 1re
        assert ws1.closed and ws1.closed[0] == 4000
        await m.send(7, {"type": "pong"})
        assert ws2.sent and not ws1.sent

    asyncio.run(run())


def test_manager_busy_flag():
    from apps.api.ws.manager import ConnectionManager
    m = ConnectionManager()
    assert not m.is_busy(3)
    m.set_busy(3, True)
    assert m.is_busy(3)
    m.set_busy(3, False)
    assert not m.is_busy(3)


# ─── Router /ws/{session_id} ──────────────────────────────────────────────


@pytest.fixture
def ws_client(monkeypatch):
    """App FastAPI isolee avec le router WS + stubs (pas de DB ni LLM)."""
    from apps.api.ws import router as wr

    saved_messages = []

    monkeypatch.setattr(wr, "get_thread_id_from_session",
                        lambda sid, db_path=None: "thread-test")
    monkeypatch.setattr(wr.crud, "get_session",
                        lambda sid, db_path=None: {"id": sid, "title": "t"})
    monkeypatch.setattr(wr.crud, "add_message",
                        lambda **kw: saved_messages.append(kw) or 1)
    monkeypatch.setattr(wr, "_notify_due_reviews", lambda sid: None)
    # Pas de resync HITL dans les tests (evite de construire le graphe reel)
    monkeypatch.setattr(wr.agent_service, "_get_pending_interrupt",
                        lambda graph, cfg: None)

    def fake_stream(**kwargs):
        yield {"token": "Bonjour", "done": False}
        yield {"token": "", "done": True,
               "metadata": {"thread_id": kwargs.get("thread_id"),
                            "method": "scaffold", "artifacts": [],
                            "tool_transparency": []},
               "interrupt": None}

    monkeypatch.setattr(wr.agent_service, "run_agent_streaming", fake_stream)

    app = FastAPI()
    app.include_router(wr.router)
    return TestClient(app), saved_messages


def test_ws_ping_pong(ws_client):
    client, _ = ws_client
    with client.websocket_connect("/ws/1?user_id=u") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_unknown_session_closed_4404(ws_client, monkeypatch):
    client, _ = ws_client
    from apps.api.ws import router as wr
    monkeypatch.setattr(wr.crud, "get_session", lambda sid, db_path=None: None)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/999?user_id=u") as ws:
            ws.receive_json()
    assert exc.value.code == 4404


def test_ws_chat_streams_tokens_then_final(ws_client):
    client, saved = ws_client
    with client.websocket_connect("/ws/5?user_id=u") as ws:
        ws.send_json({"type": "chat", "question": "salut"})
        got_token, got_final = None, None
        for _ in range(10):
            msg = ws.receive_json()
            if msg["type"] == "token":
                got_token = msg
            elif msg["type"] == "message":
                got_final = msg
                break
        assert got_token and got_token["text"] == "Bonjour"
        assert got_final["answer"] == "Bonjour"
        assert got_final["method"] == "scaffold"
        # Messages sauvegardes dans la session (liaison session ↔ WS)
        roles = [m["role"] for m in saved]
        assert "user" in roles and "assistant" in roles


def test_ws_chat_concurrent_refuse(ws_client):
    client, _ = ws_client
    from apps.api.ws import router as wr

    def slow_stream(**kwargs):
        yield {"token": "lent", "done": False}
        time.sleep(1.0)
        yield {"token": "", "done": True,
               "metadata": {"thread_id": "t", "method": "scaffold",
                            "artifacts": [], "tool_transparency": []},
               "interrupt": None}

    wr.agent_service.run_agent_streaming = slow_stream
    with client.websocket_connect("/ws/6?user_id=u") as ws:
        ws.send_json({"type": "chat", "question": "q1"})
        ws.send_json({"type": "chat", "question": "q2"})
        types = []
        for _ in range(10):
            msg = ws.receive_json()
            types.append(msg["type"])
            if msg["type"] == "message":
                break
        assert "error" in types  # q2 refuse : agent_busy


def test_ws_confirm_resume_hitl(ws_client, monkeypatch):
    """confirm → run_agent_streaming doit recevoir resume_value=True."""
    client, _ = ws_client
    from apps.api.ws import router as wr

    received_kwargs = {}

    def resume_stream(**kwargs):
        received_kwargs.update(kwargs)
        yield {"token": "OK", "done": False}
        yield {"token": "", "done": True,
               "metadata": {"thread_id": kwargs.get("thread_id"),
                            "method": "scaffold", "artifacts": [],
                            "tool_transparency": []},
               "interrupt": None}

    monkeypatch.setattr(wr.agent_service, "run_agent_streaming", resume_stream)
    with client.websocket_connect("/ws/9?user_id=u") as ws:
        ws.send_json({"type": "confirm", "accepted": True})
        final = None
        for _ in range(10):
            msg = ws.receive_json()
            if msg["type"] == "message":
                final = msg
                break
        assert final is not None
        assert received_kwargs.get("resume_value") is True
        assert received_kwargs.get("question") == ""


def test_ws_chat_interrupt_emits_confirmation(ws_client, monkeypatch):
    """Un interrupt dans le stream doit emettre confirmation_request."""
    client, _ = ws_client
    from apps.api.ws import router as wr

    def interrupt_stream(**kwargs):
        yield {"token": "", "done": True,
               "metadata": {"thread_id": "t", "method": "scaffold",
                            "artifacts": [], "tool_transparency": []},
               "interrupt": {"type": "competency_creation",
                             "question": "Veux-tu créer la compétence ?"}}

    monkeypatch.setattr(wr.agent_service, "run_agent_streaming", interrupt_stream)
    with client.websocket_connect("/ws/11?user_id=u") as ws:
        ws.send_json({"type": "chat", "question": "apprends-moi X"})
        msg = ws.receive_json()
        assert msg["type"] == "confirmation_request"
        assert msg["confirmation_type"] == "competency_creation"


# ─── run_agent_streaming : forme du done ──────────────────────────────────


def test_streaming_done_metadata_shape(monkeypatch):
    """Le done final doit contenir method/artifacts/interrupt."""
    from apps.api.services import agent_service

    class FakeSnapshot:
        values = {"method": "scaffold", "artifacts": [{"kind": "quiz"}],
                  "tool_transparency": []}
        next = ()
        tasks = ()

    class FakeGraph:
        def stream(self, inp, config=None):
            yield {"generate": {"answer": "Bonjour"}}

        def get_state(self, config):
            return FakeSnapshot()

    monkeypatch.setattr(agent_service, "get_graph", lambda: FakeGraph())
    monkeypatch.setattr(agent_service, "_build_initial_state",
                        lambda *a, **kw: {"question": "x"})

    events = list(agent_service.run_agent_streaming(
        question="salut", thread_id="t-test", user_id="u"))
    done = [e for e in events if e.get("done")]
    assert done, "doit avoir un evenement done"
    meta = done[0].get("metadata", {})
    assert meta.get("method") == "scaffold"
    assert meta.get("artifacts") == [{"kind": "quiz"}]
    assert "interrupt" in done[0]
    assert done[0]["interrupt"] is None
