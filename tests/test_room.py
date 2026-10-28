"""Room state machine tested directly with a controllable clock (no sockets, no sleeping)."""
import pytest

import server
from game_logic import STAGE_SECONDS, rotate
from server import Player, Room

ONLINE = object()  # stands in for a connected WebSocket


def human(name, online=True):
    return Player(token=f"tok-{name}", name=name, ws=ONLINE if online else None)


def room_with(*players, now=1000.0):
    room = Room(code="TEST1")
    for p in players:
        room.players[p.token] = p
    room.ever_joined = True
    room.ensure_host()
    room.created = room.updated = now
    return room


def bot(name="VEGA"):
    return Player(token=f"bot-{name}", name=name, bot=True)


def solve_with(room, now):
    """Have every owner play the optimal plan; returns the time after the last move."""
    owners = room.owners()
    for dial, direction in room.puzzle.plan():
        player = room.by_id(owners[dial])
        now += 0.2
        emit, error, _ = room.handle(player, {"type": "move", "dial": dial, "direction": direction}, now)
        assert emit and error is None
    return now


def test_ownership_split_for_one_to_four_players():
    a, b, c, d = (human(n) for n in "ABCD")
    room = room_with(a)
    assert room.owners() == [a.id] * 4
    room.players[b.token] = b
    assert room.owners() == [a.id, b.id, a.id, b.id]
    room.players[c.token] = c
    assert room.owners() == [a.id, b.id, c.id, a.id]
    room.players[d.token] = d
    assert room.owners() == [a.id, b.id, c.id, d.id]
    d.ws = None
    assert room.owners() == [a.id, b.id, c.id, a.id]


def test_host_is_first_human_and_never_a_bot():
    v, a = bot(), human("A")
    room = room_with(v, a)
    assert room.host == a.token
    a.ws = None
    room.ensure_host()
    assert room.host == a.token  # nobody else human: keep the seat for the original host
    b = human("B")
    room.players[b.token] = b
    room.ensure_host()
    assert room.host == b.token


def test_solo_player_can_start_and_finish_three_rounds():
    a = human("A")
    room = room_with(a)
    now = 1000.0
    assert room.handle(a, {"type": "start"}, now)[0]
    for stage in (1, 2, 3):
        assert room.phase == "playing" and room.puzzle.stage == stage and not room.paused
        now = solve_with(room, now)
        assert room.stage_result == "solved"
        if stage < 3:
            assert room.phase == "intermission"
            now += server.INTERMISSION_SECONDS
            assert room.tick(now)
    assert room.phase == "finished"
    assert len(room.history) == 3 and all(h["result"] == "solved" for h in room.history)
    assert room.total_score == sum(h["points"] for h in room.history) > 0


def test_non_host_cannot_start_and_unowned_move_is_rejected():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    emit, error, _ = room.handle(b, {"type": "start"}, 1000)
    assert not emit and "host" in error
    room.handle(a, {"type": "start"}, 1000)
    before = list(room.puzzle.positions)
    emit, error, _ = room.handle(b, {"type": "move", "dial": 0, "direction": 1}, 1001)
    assert not emit and "teammate" in error and room.puzzle.positions == before
    emit, error, _ = room.handle(b, {"type": "move", "dial": 1, "direction": 1}, 1001)
    assert emit and error is None and room.puzzle.positions == rotate(before, 1, 1)
    assert room.last_action["by"] == b.id and room.last_action["dial"] == 1


@pytest.mark.parametrize("msg", [
    {"type": "move", "dial": "0", "direction": 1}, {"type": "move", "dial": 0, "direction": 2},
    {"type": "move", "dial": 9, "direction": 1}, {"type": "move", "dial": True, "direction": 1},
    {"type": "move"}, {"type": "nonsense"}, {"type": None}, {},
])
def test_malformed_actions_are_ignored(msg):
    a = human("A")
    room = room_with(a)
    room.handle(a, {"type": "start"}, 1000)
    before = list(room.puzzle.positions)
    assert room.handle(a, msg, 1001) == (False, None, False)
    assert room.puzzle.positions == before


def test_moves_are_rate_limited_with_burst_allowance():
    a = human("A")
    room = room_with(a)
    room.handle(a, {"type": "start"}, 1000)
    room.puzzle.target = [9, 9, 9, 9]  # unreachable so no move ends the round
    accepted = sum(room.handle(a, {"type": "move", "dial": 0, "direction": 1}, 1000.0)[0] for _ in range(20))
    assert accepted == int(server.MOVE_BURST)
    assert room.handle(a, {"type": "move", "dial": 0, "direction": 1}, 1000.0 + 1 / server.MOVE_RATE)[0]


def test_moves_ignored_outside_play_and_while_paused():
    a = human("A")
    room = room_with(a)
    assert not room.handle(a, {"type": "move", "dial": 0, "direction": 1}, 1000)[0]
    room.handle(a, {"type": "start"}, 1000)
    room.paused = True
    assert not room.handle(a, {"type": "move", "dial": 0, "direction": 1}, 1001)[0]


def test_timer_expiry_scores_zero_then_advances_and_finishes():
    a = human("A")
    room = room_with(a)
    now = 1000.0
    room.handle(a, {"type": "start"}, now)
    for stage in (1, 2, 3):
        now += STAGE_SECONDS[stage - 1] + 0.01
        assert room.tick(now)
        assert room.stage_result == "expired" and room.last_score == 0
        if stage < 3:
            assert room.phase == "intermission"
            assert not room.tick(now + 1) or room.phase == "intermission"
            now += server.INTERMISSION_SECONDS
            room.tick(now)
            assert room.phase == "playing" and room.puzzle.stage == stage + 1
    assert room.phase == "finished" and room.total_score == 0


def test_clock_pauses_only_when_every_human_disconnects_and_resumes():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    room.handle(a, {"type": "start"}, 1000.0)
    b.ws, b.offline_since = None, 1010.0
    room.membership_changed(1010.0, room.owners())
    assert not room.paused and room.owners() == [a.id] * 4  # stations pass to the remaining player
    a.ws, a.offline_since = None, 1020.0
    room.membership_changed(1020.0, room.owners())
    assert room.paused and room.remaining == pytest.approx(STAGE_SECONDS[0] - 20)
    room.tick(1300.0)
    assert room.phase == "playing" and room.paused  # no expiry while paused
    a.ws = ONLINE
    room.membership_changed(1400.0, room.owners())
    assert not room.paused and room.end_at == pytest.approx(1400.0 + STAGE_SECONDS[0] - 20)


def test_reassignment_is_announced_mid_round():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    room.handle(a, {"type": "start"}, 1000.0)
    before = room.owners()
    b.ws = None
    room.membership_changed(1001.0, before)
    assert "Stations reassigned" in room.chat[-1]["message"]


def test_bots_only_play_their_own_stations_and_help_finish_the_round():
    a, v = human("A"), bot()
    room = room_with(a, v)
    now = 1000.0
    room.handle(a, {"type": "start"}, now)
    for _ in range(400):
        if room.phase != "playing":
            break
        before = list(room.puzzle.positions)
        now += 0.25
        room.tick(now)
        if room.puzzle.positions != before and room.phase == "playing":
            assert room.owners()[room.last_action["dial"]] == v.id
        owners = room.owners()
        mine = [m for m in room.puzzle.plan() if owners[m[0]] == a.id] if room.phase == "playing" else []
        if mine:
            room.handle(a, {"type": "move", "dial": mine[0][0], "direction": mine[0][1]}, now)
    assert room.phase == "intermission" and room.stage_result == "solved"


def test_bots_wait_while_paused_and_in_lobby():
    a, v = human("A", online=False), bot()
    room = room_with(a, v)
    assert not room.bot_turns(2000.0)
    room.begin_stage(1, 1000.0)
    assert room.paused  # no human online
    before = list(room.puzzle.positions)
    room.tick(1100.0)
    assert room.puzzle.positions == before


def test_add_and_remove_bots_rules():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    assert room.handle(b, {"type": "add_bot"}, 1000)[1]  # not host
    for _ in range(2):
        assert room.handle(a, {"type": "add_bot"}, 1000)[0]
    assert room.handle(a, {"type": "add_bot"}, 1000)[1] == "All four stations are crewed."
    bots = [p for p in room.players.values() if p.bot]
    assert len({p.name for p in bots}) == 2
    room.handle(a, {"type": "start"}, 1000)
    assert room.handle(a, {"type": "remove_bot", "id": bots[0].id}, 1001) == (False, None, False)
    room.phase = "finished"
    assert room.handle(a, {"type": "remove_bot", "id": bots[0].id}, 1002)[0]
    assert bots[0].token not in room.players
    assert room.handle(a, {"type": "remove_bot", "id": a.id}, 1003) == (False, None, False)


def test_hint_reveals_a_plan_move_and_costs_points():
    a = human("A")
    room = room_with(a)
    room.handle(a, {"type": "start"}, 1000.0)
    plan = room.puzzle.plan()
    assert room.handle(a, {"type": "hint"}, 1001.0)[0]
    assert room.hints == 1 and room.chat[-1]["kind"] == "hint"
    dial, direction = plan[0]
    assert server.STATIONS[dial] in room.chat[-1]["message"]
    assert room.handle(a, {"type": "hint"}, 1002.0)[1]  # cooldown
    solve_with(room, 1010.0)
    assert room.history[-1]["hints"] == 1
    full = server.round_points(True, room.history[-1]["seconds_left"], room.history[-1]["moves"], room.puzzle.par, 0)
    assert room.last_score == max(50, full - server.HINT_PENALTY)


def test_offline_lobby_seat_is_reclaimed_for_newcomers():
    players = [human(n) for n in "ABCD"]
    room = room_with(*players)
    assert room.seat_for_newcomer(1000.0) is not None  # all online: full
    players[1].ws, players[1].offline_since = None, 999.0
    assert room.seat_for_newcomer(1000.0) is None
    assert players[1].token not in room.players


def test_mid_game_offline_seat_is_held_for_a_grace_period():
    players = [human(n) for n in "ABCD"]
    room = room_with(*players)
    room.handle(players[0], {"type": "start"}, 1000.0)
    players[3].ws, players[3].offline_since = None, 1000.0
    assert room.seat_for_newcomer(1005.0)  # still held for reconnect
    assert room.seat_for_newcomer(1000.0 + server.OFFLINE_SEAT_GRACE) is None


def test_offline_players_pruned_from_lobby_and_host_moves():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    a.ws, a.offline_since = None, 1000.0
    room.ensure_host()
    assert room.host == b.token
    assert room.tick(1000.0 + server.LOBBY_OFFLINE_PRUNE)
    assert a.token not in room.players


def test_leave_removes_player_and_transfers_host():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    assert room.handle(a, {"type": "leave"}, 1000.0) == (True, None, True)
    assert a.token not in room.players and room.host == b.token


def test_chat_sanitised_trimmed_and_throttled():
    a = human("A")
    room = room_with(a)
    assert room.handle(a, {"type": "chat", "message": "  hi\x00\x07 <b>crew</b>‮ " + "x" * 400}, 1000.0)[0]
    msg = room.chat[-1]
    assert msg["name"] == "A" and msg["kind"] == "player"
    assert "\x00" not in msg["message"] and "‮" not in msg["message"]
    assert len(msg["message"]) == 180 and msg["message"].startswith("hi <b>crew</b>")
    assert not room.handle(a, {"type": "chat", "message": "again"}, 1000.1)[0]
    assert not room.handle(a, {"type": "chat", "message": "   "}, 1002.0)[0]
    assert room.handle(a, {"type": "chat", "message": "again"}, 1002.0)[0]


def test_chat_history_is_capped():
    a = human("A")
    room = room_with(a)
    for i in range(server.CHAT_HISTORY + 20):
        room.log(f"m{i}")
    assert len(room.chat) == server.CHAT_HISTORY and room.chat[-1]["message"] == f"m{server.CHAT_HISTORY + 19}"


def test_snapshot_exposes_only_the_viewers_session_token():
    a, b = human("A"), human("B")
    room = room_with(a, b)
    snap = room.snapshot(a.token)
    assert snap["session"] == a.token and snap["you"] == a.id
    assert b.token not in str(snap)
    assert room.snapshot("not-a-member")["session"] is None


def test_restart_resets_score_history_and_chat():
    a = human("A")
    room = room_with(a)
    room.handle(a, {"type": "start"}, 1000.0)
    solve_with(room, 1000.0)
    assert room.total_score > 0
    room.phase = "finished"
    room.handle(a, {"type": "start"}, 2000.0)
    assert room.total_score == 0 and room.history == [] and room.puzzle.stage == 1
    assert room.chat[-1]["message"].startswith("Round 1")


def test_room_expiry_rules():
    fresh = Room(code="AAAAA", created=0.0, updated=0.0)
    assert not fresh.expired(server.ROOM_UNUSED_TTL - 1)
    assert fresh.expired(server.ROOM_UNUSED_TTL + 1)
    a = human("A", online=False)
    room = room_with(a, now=0.0)
    assert not room.expired(10.0)
    assert room.expired(10.0 + server.ROOM_ABANDONED_TTL + 1)
    busy = room_with(human("B"), now=0.0)
    assert not busy.expired(server.ROOM_ABANDONED_TTL * 2)
    assert busy.expired(server.ROOM_IDLE_TTL + 1)


def test_every_chat_message_bumps_revision_so_clients_rerender():
    """Regression: chat used to arrive without a revision change and was never drawn."""
    a = human("A")
    room = room_with(a)
    before = room.revision
    room.handle(a, {"type": "chat", "message": "hello"}, 1000.0)
    assert room.revision > before
