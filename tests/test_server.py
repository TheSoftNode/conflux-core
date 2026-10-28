"""HTTP routes and the WebSocket protocol, exercised through the real ASGI app."""
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
from game_logic import rotate
from server import ROOMS, app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def until(ws, predicate, limit=60):
    """Read messages until one satisfies predicate (ticker snapshots may interleave)."""
    for _ in range(limit):
        msg = ws.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError("expected message never arrived")


def state(ws, predicate=lambda s: True):
    return until(ws, lambda m: m.get("type") == "state" and predicate(m))


def join(ws, name, token=""):
    ws.send_json({"type": "join", "name": name, "token": token})
    return state(ws)


def new_room(client):
    return client.post("/api/rooms").json()["code"]


def closed_with(ws):
    with pytest.raises(WebSocketDisconnect) as info:
        for _ in range(10):
            ws.receive_json()
    return info.value.code


# ---------------------------------------------------------------- HTTP
def test_index_health_and_headers(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "{{VERSION}}" not in page.text and f"app.js?v={server.VERSION}" in page.text
    assert page.headers["cache-control"] == "no-cache"
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    health = client.get("/health").json()
    assert health["ok"] is True and health["version"] == server.VERSION and health["rooms"] == 0
    assert client.get("/favicon.ico").status_code == 200


def test_create_room_codes_are_unique_and_unambiguous(client):
    codes = {new_room(client) for _ in range(10)}
    assert len(codes) == 10
    for code in codes:
        assert len(code) == 5 and set(code) <= set(server.ROOM_CHARS)
        assert not set(code) & set("01IO")


def test_room_creation_is_rate_limited_per_client(client):
    for _ in range(server.CREATE_LIMIT):
        assert client.post("/api/rooms").status_code == 200
    blocked = client.post("/api/rooms")
    assert blocked.status_code == 429 and "Too many" in blocked.json()["detail"]
    other = client.post("/api/rooms", headers={"x-forwarded-for": "203.0.113.9"})
    assert other.status_code == 200


def test_room_capacity_limit(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_ROOMS", 2)
    assert client.post("/api/rooms").status_code == 200
    assert client.post("/api/rooms").status_code == 200
    assert client.post("/api/rooms").status_code == 503


# ---------------------------------------------------------------- join / reject
def test_unknown_room_gets_fatal_error_and_terminal_close_code(client):
    with client.websocket_connect("/ws/ZZZZZ") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["fatal"] and "not found" in msg["message"]
        assert closed_with(ws) == server.CLOSE_NOT_FOUND


@pytest.mark.parametrize("first", [{"type": "chat", "message": "hi"}, [], "garbage"])
def test_first_message_must_be_join(client, first):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_text(first if isinstance(first, str) else json.dumps(first))
        msg = ws.receive_json()
        assert msg["fatal"] and "Join" in msg["message"]
        assert closed_with(ws) == server.CLOSE_FATAL


def test_join_timeout(client, monkeypatch):
    monkeypatch.setattr(server, "JOIN_TIMEOUT", 0.2)
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        assert ws.receive_json()["message"] == "Join timed out."
        assert closed_with(ws) == server.CLOSE_FATAL


def test_lowercase_code_and_name_sanitising(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code.lower()}") as ws:
        snap = join(ws, "  <Nova>\x00 the\tGreat and Powerful  ")
        me = snap["players"][0]
        assert me["name"] == "Nova the Great and"[:18] and "<" not in me["name"]
        assert snap["code"] == code and snap["protocol"] == server.PROTOCOL
    with client.websocket_connect(f"/ws/{code}") as ws:
        assert join(ws, "")["players"][-1]["name"] == "Player"


def test_fifth_player_is_rejected_cleanly_without_reconnect_loop(client):
    code = new_room(client)
    sockets = [client.websocket_connect(f"/ws/{code}") for _ in range(4)]
    try:
        for i, ws in enumerate(sockets):
            ws.__enter__()
            join(ws, f"P{i}")
        with client.websocket_connect(f"/ws/{code}") as extra:
            extra.send_json({"type": "join", "name": "Late"})
            msg = until(extra, lambda m: m["type"] == "error")
            assert msg["fatal"] and "full" in msg["message"]
            assert closed_with(extra) == server.CLOSE_FATAL
    finally:
        for ws in sockets:
            ws.__exit__(None, None, None)


def test_ghost_lobby_seats_are_reclaimed(client):
    """Regression: four players leaving the lobby used to lock the room forever."""
    code = new_room(client)
    for i in range(4):
        with client.websocket_connect(f"/ws/{code}") as ws:
            join(ws, f"P{i}")
    assert len(ROOMS[code].players) == 4 and not ROOMS[code].humans_online()
    with client.websocket_connect(f"/ws/{code}") as ws:
        snap = join(ws, "Newcomer")
        assert any(p["name"] == "Newcomer" for p in snap["players"])
        assert snap["host"] == snap["you"]


def test_bot_token_cannot_be_hijacked(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as host:
        join(host, "Host")
        host.send_json({"type": "add_bot"})
        state(host, lambda s: len(s["players"]) == 2)
        bot_token = next(t for t, p in ROOMS[code].players.items() if p.bot)
        with client.websocket_connect(f"/ws/{code}") as thief:
            snap = join(thief, "Thief", bot_token)
            assert snap["session"] != bot_token
            assert ROOMS[code].players[bot_token].ws is None


# ---------------------------------------------------------------- robustness
@pytest.mark.parametrize("payload", ["[]", "null", "42", "{not json", '"text"', '{"type": 5}'])
def test_malformed_messages_do_not_drop_the_connection(client, payload):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        join(ws, "Nova")
        ws.send_text(payload)
        ws.send_json({"type": "chat", "message": "still here"})
        assert state(ws, lambda s: s["chat"] and s["chat"][-1]["message"] == "still here")


def test_ping_gets_pong(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        join(ws, "Nova")
        ws.send_json({"type": "ping"})
        assert until(ws, lambda m: m["type"] == "pong")


def test_oversized_and_binary_messages_close_the_socket(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        join(ws, "Nova")
        ws.send_text(json.dumps({"type": "chat", "message": "x" * 5000}))
        assert closed_with(ws) == 1003
    with client.websocket_connect(f"/ws/{code}") as ws:
        join(ws, "Mira")
        ws.send_bytes(b"\x00\x01")
        assert closed_with(ws) == 1003


# ---------------------------------------------------------------- gameplay over sockets
def test_two_players_sync_ownership_and_moves(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as a:
        one = join(a, "Alpha")
        assert one["phase"] == "lobby" and one["session"] != one["you"]
        with client.websocket_connect(f"/ws/{code}") as b:
            two = join(b, "Beta")
            one = state(a, lambda s: len(s["players"]) == 2)
            assert one["host"] == one["you"] != two["you"]
            assert two["session"] != one["session"] and one["session"] not in json.dumps(two)
            b.send_json({"type": "start"})
            assert "host" in until(b, lambda m: m["type"] == "error")["message"]
            a.send_json({"type": "start"})
            one = state(a, lambda s: s["phase"] == "playing")
            two = state(b, lambda s: s["phase"] == "playing")
            assert one["positions"] == two["positions"] and one["target"] == two["target"]
            assert one["owners"] == [one["you"], two["you"], one["you"], two["you"]]
            assert one["par"] >= 1 and one["duration"] == 90 and one["stations"] == list(server.STATIONS)
            original = one["positions"]
            a.send_json({"type": "move", "dial": 1, "direction": 1})
            err = until(a, lambda m: m["type"] == "error")
            assert "EMBER" in err["message"] and not err.get("fatal")
            assert ROOMS[code].puzzle.positions == original
            b.send_json({"type": "move", "dial": 1, "direction": 1})
            expected = rotate(original, 1, 1)
            one = state(a, lambda s: s["positions"] == expected)
            two = state(b, lambda s: s["positions"] == expected)
            assert one["last_action"]["by"] == two["you"] and one["moves"] == 1


def test_solo_run_three_rounds_then_replay(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        me = join(ws, "Solo")
        ws.send_json({"type": "start"})
        snap = state(ws, lambda s: s["phase"] == "playing")
        assert not snap["paused"] and snap["owners"] == [me["you"]] * 4
        for stage in (1, 2, 3):
            room = ROOMS[code]
            if stage > 1:
                room.next_at = 0  # skip the intermission wait
                snap = state(ws, lambda s: s["phase"] == "playing" and s["stage"] == stage)
            for p in room.players.values():
                p.allowance = server.MOVE_BURST  # the skipped intermission would have refilled it
            for dial, direction in room.puzzle.plan():
                ws.send_json({"type": "move", "dial": dial, "direction": direction})
            snap = state(ws, lambda s: s["result"] == "solved" and s["stage"] == stage)
            assert snap["phase"] == ("finished" if stage == 3 else "intermission")
            assert snap["history"][-1]["moves"] == snap["history"][-1]["par"]
        assert len(snap["history"]) == 3 and snap["score"] == sum(h["points"] for h in snap["history"])
        ws.send_json({"type": "start"})
        snap = state(ws, lambda s: s["phase"] == "playing" and s["score"] == 0 and s["stage"] == 1)
        assert snap["history"] == []


def test_reconnect_with_token_restores_identity_and_kicks_old_tab(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as first:
        snap = join(first, "Nova")
        with client.websocket_connect(f"/ws/{code}") as second:
            again = join(second, "Ignored", snap["session"])
            assert again["you"] == snap["you"] and again["players"][0]["name"] == "Nova"
            assert len(again["players"]) == 1
            msg = until(first, lambda m: m["type"] == "error")
            assert msg["fatal"] and "another tab" in msg["message"]
            assert closed_with(first) == server.CLOSE_REPLACED


def test_disconnect_reassigns_and_reconnect_restores(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as a:
        one = join(a, "Alpha")
        with client.websocket_connect(f"/ws/{code}") as b:
            two = join(b, "Beta")
            a.send_json({"type": "start"})
            state(a, lambda s: s["phase"] == "playing")
        snap = state(a, lambda s: not any(p["online"] for p in s["players"] if p["id"] == two["you"]))
        assert snap["owners"] == [one["you"]] * 4 and not snap["paused"]
        assert any("reassigned" in m["message"] for m in snap["chat"])
        with client.websocket_connect(f"/ws/{code}") as b2:
            back = join(b2, "Beta", two["session"])
            assert back["you"] == two["you"] and back["owners"] == [one["you"], two["you"]] * 2


def test_everyone_leaving_pauses_and_returning_resumes(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as a:
        snap = join(a, "Alpha")
        a.send_json({"type": "start"})
        state(a, lambda s: s["phase"] == "playing")
    room = ROOMS[code]
    assert room.paused and room.phase == "playing"
    with client.websocket_connect(f"/ws/{code}") as a2:
        back = join(a2, "Alpha", snap["session"])
        assert not back["paused"] and back["you"] == snap["you"]


def test_late_joiner_enters_running_game(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as a:
        one = join(a, "Alpha")
        a.send_json({"type": "start"})
        state(a, lambda s: s["phase"] == "playing")
        with client.websocket_connect(f"/ws/{code}") as b:
            two = join(b, "Late")
            assert two["phase"] == "playing" and two["you"] in two["owners"]
            assert "mid-run" in " ".join(m["message"] for m in two["chat"])
            assert two["host"] == one["you"]


def test_leave_message_removes_player_and_closes(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as a:
        one = join(a, "Alpha")
        with client.websocket_connect(f"/ws/{code}") as b:
            two = join(b, "Beta")
            state(a, lambda s: len(s["players"]) == 2)
            a.send_json({"type": "leave"})
            snap = state(b, lambda s: len(s["players"]) == 1)
            assert snap["host"] == two["you"] and one["you"] not in json.dumps(snap["players"])


def test_quick_play_with_ai_crew_over_socket(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        me = join(ws, "Nova")
        ws.send_json({"type": "add_bot"})
        snap = state(ws, lambda s: len(s["players"]) == 2)
        bot = next(p for p in snap["players"] if p["bot"])
        assert bot["online"] and not bot["is_host"]
        ws.send_json({"type": "start"})
        snap = state(ws, lambda s: s["phase"] == "playing")
        assert snap["owners"] == [me["you"], bot["id"], me["you"], bot["id"]]
        room = ROOMS[code]
        mine = [m for m in room.puzzle.plan() if snap["owners"][m[0]] == me["you"]]
        for dial, direction in mine:
            ws.send_json({"type": "move", "dial": dial, "direction": direction})
        for p in room.players.values():
            p.next_action = 0  # let the AI act on the next tick
        snap = until(ws, lambda m: m.get("result") == "solved", limit=400)
        assert snap["phase"] == "intermission"


def test_hint_over_socket(client):
    code = new_room(client)
    with client.websocket_connect(f"/ws/{code}") as ws:
        join(ws, "Nova")
        ws.send_json({"type": "hint"})  # ignored in lobby
        ws.send_json({"type": "start"})
        state(ws, lambda s: s["phase"] == "playing")
        ws.send_json({"type": "hint"})
        snap = state(ws, lambda s: s["hints"] == 1)
        assert snap["chat"][-1]["kind"] == "hint"
