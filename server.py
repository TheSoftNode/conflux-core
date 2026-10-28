"""Room-based realtime multiplayer server for CONFLUX CORE.

Run: uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
All room state lives in this process, so deploy exactly one worker/instance.
"""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import logging
import os
import random
import re
import secrets
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game_logic import (N_DIALS, N_STAGES, STAGE_SECONDS, STATIONS, SYMBOLS, HINT_PENALTY,
                        Puzzle, round_points)

VERSION = "4.0.0"
PROTOCOL = 2
ROOT = os.path.dirname(os.path.abspath(__file__))
ROOM_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_MAX = 4
MAX_ROOMS = int(os.environ.get("CONFLUX_MAX_ROOMS", "500"))
ROOM_IDLE_TTL = 3 * 60 * 60        # any room with no activity
ROOM_ABANDONED_TTL = 20 * 60       # no human connected
ROOM_UNUSED_TTL = 10 * 60          # created but nobody ever joined
LOBBY_OFFLINE_PRUNE = 60           # offline players leave the lobby list after this
OFFLINE_SEAT_GRACE = 20            # mid-game seats are held this long for reconnects
OFFLINE_PRUNE = 10 * 60            # offline players are forgotten after this in any phase
INTERMISSION_SECONDS = 6
JOIN_TIMEOUT = 10
MAX_MESSAGE_BYTES = 2048
CHAT_HISTORY = 40
CHAT_INTERVAL = 0.5
HINT_COOLDOWN = 4.0
MOVE_BURST = 6.0                   # token bucket: short bursts allowed...
MOVE_RATE = 8.0                    # ...refilled at this many moves per second
CREATE_LIMIT = int(os.environ.get("CONFLUX_CREATE_LIMIT", "15"))
CREATE_WINDOW = 60.0
BOT_NAMES = ("VEGA", "LYRA", "ORION")
BOT_DELAY = (1.5, 2.6)
TICK_SECONDS = 0.25
SEND_TIMEOUT = 10.0
BROADCAST_EVERY = 0.5
CLOSE_FATAL = 4000
CLOSE_REPLACED = 4001
CLOSE_NOT_FOUND = 4004
ALLOWED_ORIGINS = {o.strip().rstrip('/') for o in os.environ.get("CONFLUX_ALLOWED_ORIGINS", "").split(",") if o.strip()}

log = logging.getLogger("conflux")
ROOMS: dict[str, 'Room'] = {}
CREATE_LOG: dict[str, deque[float]] = {}
_CONTROL = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]")


def clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\t\r\n\f\v]", " ", str(value or ""))
    return re.sub(r"\s+", " ", _CONTROL.sub("", text)).strip()[:limit].rstrip()


def clean_name(value: Any) -> str:
    return clean_text(re.sub(r"[<>]", "", str(value or "")), 18) or "Player"


class Outbox:
    """Per-connection writer. Snapshots are conflated (only the newest is sent), so a slow
    client never delays the ticker or other players; one-off messages are queued in order."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.latest: dict[str, Any] | None = None
        self.queue: deque[dict[str, Any]] = deque()
        self.wake = asyncio.Event()
        self.task = asyncio.create_task(self._run())

    def state(self, payload: dict[str, Any]) -> None:
        self.latest = payload
        self.wake.set()

    def message(self, payload: dict[str, Any]) -> None:
        self.queue.append(payload)
        self.wake.set()

    async def _run(self) -> None:
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                while self.queue:
                    await asyncio.wait_for(self.ws.send_json(self.queue.popleft()), SEND_TIMEOUT)
                if self.latest is not None:
                    payload, self.latest = self.latest, None
                    await asyncio.wait_for(self.ws.send_json(payload), SEND_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:  # dead or too slow: closing ends the receive loop, which cleans up
            await _close(self.ws, 1011)

    def stop(self) -> None:
        self.task.cancel()


@dataclass
class Player:
    token: str
    name: str
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    ws: WebSocket | None = None
    outbox: Outbox | None = None
    bot: bool = False
    offline_since: float = 0.0
    allowance: float = MOVE_BURST
    allowance_at: float = 0.0
    last_chat: float = 0.0
    next_action: float = 0.0

    @property
    def online(self) -> bool:
        return self.bot or self.ws is not None

    def take_move(self, now: float) -> bool:
        self.allowance = min(MOVE_BURST, self.allowance + (now - self.allowance_at) * MOVE_RATE)
        self.allowance_at = now
        if self.allowance < 1:
            return False
        self.allowance -= 1
        return True


@dataclass
class Room:
    code: str
    host: str | None = None
    players: dict[str, Player] = field(default_factory=dict)
    phase: str = "lobby"
    puzzle: Puzzle | None = None
    total_score: int = 0
    last_score: int = 0
    stage_result: str = ""
    end_at: float = 0.0
    remaining: float = 0.0
    next_at: float = 0.0
    paused: bool = False
    revision: int = 0
    hints: int = 0
    last_hint: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)
    last_action: dict[str, Any] | None = None
    chat: list[dict[str, Any]] = field(default_factory=list)
    created: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.monotonic)
    abandoned_since: float = 0.0
    ever_joined: bool = False
    last_broadcast: float = 0.0
    bot_chat_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # -- membership -------------------------------------------------------
    def active(self) -> list[Player]:
        return [p for p in self.players.values() if p.online]

    def humans_online(self) -> list[Player]:
        return [p for p in self.players.values() if not p.bot and p.ws is not None]

    def owners(self) -> list[str | None]:
        available = [p.id for p in self.active()]
        return [available[i % len(available)] if available else None for i in range(N_DIALS)]

    def by_id(self, public_id: Any) -> Player | None:
        return next((p for p in self.players.values() if p.id == public_id), None)

    def ensure_host(self) -> None:
        """Host is always a human; prefer one who is connected."""
        current = self.players.get(self.host or "")
        if current and not current.bot and current.ws is not None:
            return
        online = self.humans_online()
        if online:
            if current is not None:
                self.log(f"{online[0].name} is now the host.")
            self.host = online[0].token
        elif current is None or current.bot:
            humans = [p for p in self.players.values() if not p.bot]
            self.host = humans[0].token if humans else None

    def seat_for_newcomer(self, now: float) -> str | None:
        """Free a seat if possible; return an error message if the room is full."""
        if len(self.players) < ROOM_MAX:
            return None
        grace = 0 if self.phase in ("lobby", "finished") else OFFLINE_SEAT_GRACE
        stale = [p for p in self.players.values()
                 if not p.bot and p.ws is None and now - p.offline_since >= grace]
        if stale:
            oldest = min(stale, key=lambda p: p.offline_since)
            del self.players[oldest.token]
            return None
        return "Room is full (4 crew). Ask the host for a new room."

    def remove(self, token: str) -> None:
        self.players.pop(token, None)
        if self.host == token:
            self.host = None
        self.ensure_host()

    def membership_changed(self, now: float, before: list[str | None]) -> None:
        self.update_pause(now)
        after = self.owners()
        if self.phase == "playing" and before != after and any(after):
            names = {p.id: p.name for p in self.players.values()}
            parts = []
            for pid in dict.fromkeys(a for a in after if a):
                owned = [STATIONS[i] for i, a in enumerate(after) if a == pid]
                parts.append(f"{names.get(pid, '?')}: {', '.join(owned)}")
            self.log("Stations reassigned — " + " · ".join(parts))
        self.revision += 1
        self.updated = now

    def update_pause(self, now: float) -> None:
        """The clock runs while at least one human is connected."""
        if self.phase != "playing":
            return
        humans = len(self.humans_online())
        if not self.paused and humans == 0:
            self.remaining = max(0.0, self.end_at - now)
            self.paused = True
            self.log("Everyone disconnected. Clock paused.")
        elif self.paused and humans > 0:
            self.paused = False
            self.end_at = now + self.remaining
            self.log("Crew reconnected. Countdown resumed.")

    # -- state ------------------------------------------------------------
    def seconds_left(self, now: float) -> float:
        if self.phase == "playing":
            return self.remaining if self.paused else max(0.0, self.end_at - now)
        if self.phase == "intermission":
            return max(0.0, self.next_at - now)
        return 0.0

    def snapshot(self, token: str | None = None) -> dict[str, Any]:
        now = time.monotonic()
        puzzle = self.puzzle
        me = self.players.get(token or "")
        host = self.players.get(self.host or "")
        return {
            "type": "state", "protocol": PROTOCOL, "version": VERSION,
            "code": self.code, "phase": self.phase,
            "you": me.id if me else None,
            "session": token if me else None,
            "host": host.id if host else None,
            "revision": self.revision,
            "players": [
                {"id": p.id, "name": p.name, "online": p.online, "bot": p.bot,
                 "is_host": p.token == self.host} for p in self.players.values()
            ],
            "max_players": ROOM_MAX,
            "owners": self.owners(),
            "stations": STATIONS,
            "symbols": SYMBOLS,
            "target": list(puzzle.target) if puzzle else None,
            "positions": list(puzzle.positions) if puzzle else None,
            "stage": puzzle.stage if puzzle else 0,
            "stages": N_STAGES,
            "seconds": round(self.seconds_left(now), 1),
            "duration": STAGE_SECONDS[puzzle.stage - 1] if puzzle else 0,
            "paused": self.paused,
            "score": self.total_score, "last_score": self.last_score,
            "moves": puzzle.moves if puzzle else 0,
            "par": puzzle.par if puzzle else 0,
            "hints": self.hints, "hint_penalty": HINT_PENALTY,
            "result": self.stage_result,
            "history": self.history,
            "last_action": self.last_action,
            "chat": self.chat[-CHAT_HISTORY:],
        }

    def log(self, message: str, speaker: str = "SYSTEM", kind: str = "system") -> None:
        self.chat.append({"id": secrets.token_hex(4), "name": speaker, "message": message, "kind": kind})
        del self.chat[:-CHAT_HISTORY]
        self.revision += 1  # clients re-render chat only when the revision changes

    # -- game flow --------------------------------------------------------
    def begin_run(self, now: float) -> None:
        self.total_score = 0
        self.last_score = 0
        self.history = []
        self.chat = []
        self.begin_stage(1, now)

    def begin_stage(self, stage: int, now: float) -> None:
        self.puzzle = Puzzle.new(stage)
        self.phase = "playing"
        self.remaining = float(STAGE_SECONDS[stage - 1])
        self.end_at = now + self.remaining
        self.paused = not self.humans_online()
        self.stage_result = ""
        self.hints = 0
        self.last_action = None
        for p in self.players.values():
            if p.bot:
                p.next_action = now + random.uniform(*BOT_DELAY) + 1.0
        self.revision += 1
        self.log(f"Round {stage} is live — par {self.puzzle.par} moves. Stabilize the core!")

    def finish_stage(self, won: bool, now: float) -> None:
        assert self.puzzle is not None
        left = self.seconds_left(now)
        puzzle = self.puzzle
        self.last_score = round_points(won, left, puzzle.moves, puzzle.par, self.hints)
        self.total_score += self.last_score
        self.stage_result = "solved" if won else "expired"
        self.history.append({"stage": puzzle.stage, "result": self.stage_result, "points": self.last_score,
                             "moves": puzzle.moves, "par": puzzle.par, "hints": self.hints,
                             "seconds_left": int(left) if won else 0})
        self.log(f"Core stabilized! +{self.last_score} points." if won
                 else "Time expired. The core lost coherence.")
        self.paused = False
        if puzzle.stage >= N_STAGES:
            self.phase = "finished"
            self.log(f"Run complete. Final score {self.total_score}.")
        else:
            self.phase = "intermission"
            self.next_at = now + INTERMISSION_SECONDS
        self.revision += 1

    def apply_move(self, player: Player, dial: int, direction: int, now: float) -> None:
        assert self.puzzle is not None
        self.last_action = {"by": player.id, "dial": dial, "direction": direction, "revision": self.revision + 1}
        solved = self.puzzle.move(dial, direction)
        self.revision += 1
        if solved:
            self.finish_stage(True, now)

    def bot_turns(self, now: float) -> bool:
        if self.phase != "playing" or self.paused or not self.puzzle:
            return False
        acted = False
        for bot in [p for p in self.players.values() if p.bot]:
            if self.phase != "playing" or now < bot.next_action:
                continue
            owners = self.owners()
            plan = self.puzzle.plan()
            mine = [m for m in plan if owners[m[0]] == bot.id]
            if mine:
                bot.next_action = now + random.uniform(*BOT_DELAY)
                self.apply_move(bot, *mine[0], now)
                acted = True
            else:
                bot.next_action = now + 1.0
                humans = [p.name for p in self.humans_online() if p.id in owners]
                if plan and humans and now - self.bot_chat_at > 12:
                    self.bot_chat_at = now
                    self.log(f"My rings are set. Over to you, {humans[0]}.", bot.name, "bot")
                    acted = True
        return acted

    def tick(self, now: float) -> bool:
        """Advance timers and AI crew. Returns True if a state change needs broadcasting."""
        changed = False
        if self.phase == "playing" and not self.paused and now >= self.end_at:
            self.finish_stage(False, now)
            changed = True
        elif self.phase == "intermission" and now >= self.next_at:
            assert self.puzzle
            self.begin_stage(self.puzzle.stage + 1, now)
            changed = True
        if self.bot_turns(now):
            changed = True
        prune = LOBBY_OFFLINE_PRUNE if self.phase in ("lobby", "finished") else OFFLINE_PRUNE
        stale = [t for t, p in self.players.items()
                 if not p.bot and p.ws is None and now - p.offline_since >= prune]
        if stale:
            before = self.owners()
            for t in stale:
                self.remove(t)
            self.membership_changed(now, before)
            changed = True
        if changed:
            self.updated = now
        return changed

    def expired(self, now: float) -> bool:
        if self.humans_online():
            self.abandoned_since = 0.0
        elif not self.abandoned_since:
            self.abandoned_since = now
        if now - self.updated > ROOM_IDLE_TTL:
            return True
        if not self.ever_joined:
            return now - self.created > ROOM_UNUSED_TTL
        return bool(self.abandoned_since) and now - self.abandoned_since > ROOM_ABANDONED_TTL

    # -- client actions ---------------------------------------------------
    def handle(self, player: Player, msg: dict[str, Any], now: float) -> tuple[bool, str | None, bool]:
        """Apply one client message. Returns (broadcast, error_for_sender, sender_left)."""
        action = msg.get("type")
        is_host = player.token == self.host
        if action == "move":
            if self.phase != "playing" or self.paused or not self.puzzle:
                return False, None, False
            dial, direction = msg.get("dial"), msg.get("direction")
            if type(dial) is not int or type(direction) is not int or not 0 <= dial < N_DIALS or direction not in (-1, 1):
                return False, None, False
            if self.owners()[dial] != player.id:
                return False, f"{STATIONS[dial]} is assigned to a teammate.", False
            if not player.take_move(now):
                return False, None, False
            self.apply_move(player, dial, direction, now)
            return True, None, False
        if action == "chat":
            content = clean_text(msg.get("message"), 180)
            if not content or now - player.last_chat < CHAT_INTERVAL:
                return False, None, False
            player.last_chat = now
            self.log(content, player.name, "player")
            return True, None, False
        if action == "start":
            if not is_host:
                return False, "Only the host can start the reactor.", False
            if self.phase not in ("lobby", "finished"):
                return False, None, False
            self.begin_run(now)
            return True, None, False
        if action == "hint":
            if self.phase != "playing" or self.paused or not self.puzzle:
                return False, None, False
            if now - self.last_hint < HINT_COOLDOWN:
                return False, "Hint systems recharging…", False
            plan = self.puzzle.plan()
            owners = self.owners()
            dial, direction = next((m for m in plan if owners[m[0]] == player.id), plan[0])
            self.last_hint = now
            self.hints += 1
            owner = self.by_id(owners[dial])
            who = "you" if owner is player else (owner.name if owner else "a teammate")
            self.log(f"HINT for {player.name} (−{HINT_PENALTY}): {STATIONS[dial]} {'+' if direction > 0 else '−'} "
                     f"({who}). {len(plan)} move{'s' if len(plan) != 1 else ''} from stable.", "SYSTEM", "hint")
            self.revision += 1
            return True, None, False
        if action == "add_bot":
            if not is_host:
                return False, "Only the host can add AI crew.", False
            if self.phase not in ("lobby", "finished"):
                return False, "Add AI crew between runs.", False
            if self.seat_for_newcomer(now):
                return False, "All four stations are crewed.", False
            used = {p.name for p in self.players.values()}
            name = next((n for n in BOT_NAMES if n not in used), f"UNIT-{len(self.players) + 1}")
            bot = Player(token="bot-" + secrets.token_hex(8), name=name, bot=True)
            self.players[bot.token] = bot
            self.log(f"AI crewmate {name} is online.")
            self.membership_changed(now, self.owners())
            return True, None, False
        if action == "remove_bot":
            target = self.by_id(msg.get("id"))
            if not is_host or target is None or not target.bot or self.phase not in ("lobby", "finished"):
                return False, None, False
            self.remove(target.token)
            self.log(f"AI crewmate {target.name} powered down.")
            self.membership_changed(now, self.owners())
            return True, None, False
        if action == "leave":
            before = self.owners()
            self.remove(player.token)
            self.log(f"{player.name} left the room.")
            self.membership_changed(now, before)
            return True, None, True
        return False, None, False


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await asyncio.wait_for(ws.send_json(payload), timeout=5)
    except Exception:  # The receive loop for that socket performs cleanup.
        pass


def broadcast(room: Room) -> None:
    """Queue a fresh snapshot for every connected player (never blocks)."""
    room.last_broadcast = time.monotonic()
    for p in room.players.values():
        if p.ws is not None and p.outbox is not None:
            p.outbox.state(room.snapshot(p.token))


async def tick_all(now: float) -> None:
    for code, room in list(ROOMS.items()):
        try:
            async with room.lock:
                if room.expired(now):
                    ROOMS.pop(code, None)
                    sockets = [p.ws for p in room.players.values() if p.ws is not None]
                    for ws in sockets:
                        asyncio.create_task(_close(ws, CLOSE_NOT_FOUND))
                    continue
                changed = room.tick(now)
                timed = room.phase in ("playing", "intermission") and not room.paused
                emit = changed or (timed and now - room.last_broadcast >= BROADCAST_EVERY)
            if emit:
                broadcast(room)
        except Exception:
            log.exception("Ticker failed for room %s", code)


async def _close(ws: WebSocket, code: int) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


async def ticker() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        await tick_all(time.monotonic())


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(ticker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="CONFLUX CORE", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob:; connect-src 'self' ws: wss:; base-uri 'self'; "
                                "form-action 'self'; object-src 'none'"),
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    return response


app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")


class CreateResponse(BaseModel):
    code: str


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8") as f:
        html = f.read().replace("{{VERSION}}", VERSION)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(ROOT, "static", "favicon.svg"), media_type="image/svg+xml")


@app.get("/health")
async def health():
    return {"ok": True, "version": VERSION, "rooms": len(ROOMS),
            "players_online": sum(len(r.humans_online()) for r in ROOMS.values())}


@app.post("/api/rooms", response_model=CreateResponse)
async def create_room(request: Request):
    now = time.monotonic()
    ip = client_ip(request)
    history = CREATE_LOG.setdefault(ip, deque())
    while history and now - history[0] > CREATE_WINDOW:
        history.popleft()
    if len(history) >= CREATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many rooms created. Wait a minute and try again.")
    if len(CREATE_LOG) > 5000:
        for key in [k for k, v in CREATE_LOG.items() if not v or now - v[-1] > CREATE_WINDOW]:
            CREATE_LOG.pop(key, None)
    if len(ROOMS) >= MAX_ROOMS:
        raise HTTPException(status_code=503, detail="All reactor chambers are busy. Try again shortly.")
    for _ in range(20):
        code = "".join(secrets.choice(ROOM_CHARS) for _ in range(5))
        if code not in ROOMS:
            ROOMS[code] = Room(code=code)
            history.append(now)
            return CreateResponse(code=code)
    raise HTTPException(status_code=503, detail="Could not allocate a room.")  # pragma: no cover


class ProtocolError(Exception):
    pass


async def read_message(ws: WebSocket) -> dict[str, Any] | None:
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    raw = message.get("text")
    if raw is None:
        raise ProtocolError("binary frames are not supported")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def reject(ws: WebSocket, message: str, code: int) -> None:
    await _send(ws, {"type": "error", "message": message, "fatal": True})
    await _close(ws, code)


def origin_allowed(origin: str | None) -> bool:
    return not ALLOWED_ORIGINS or (origin or "").rstrip('/') in ALLOWED_ORIGINS


@app.websocket("/ws/{code}")
async def room_socket(ws: WebSocket, code: str):
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    room = ROOMS.get(code.upper()[:8])
    if room is None:
        await reject(ws, "Room not found. Check the code or create a new room.", CLOSE_NOT_FOUND)
        return

    token: str | None = None
    outbox: Outbox | None = None
    try:
        try:
            msg = await asyncio.wait_for(read_message(ws), timeout=JOIN_TIMEOUT)
        except asyncio.TimeoutError:
            await reject(ws, "Join timed out.", CLOSE_FATAL)
            return
        if not msg or msg.get("type") != "join":
            await reject(ws, "Join the room first.", CLOSE_FATAL)
            return
        name = clean_name(msg.get("name"))
        requested = msg.get("token")
        requested = requested[:64] if isinstance(requested, str) else ""
        error = None
        replaced: WebSocket | None = None
        outbox = Outbox(ws)
        async with room.lock:
            now = time.monotonic()
            before = room.owners()
            existing = room.players.get(requested) if requested else None
            if existing is not None and not existing.bot:
                token = requested
                replaced, existing.ws = existing.ws, ws
                if existing.outbox:
                    existing.outbox.stop()
                existing.outbox = outbox
                existing.offline_since = 0.0
                room.log(f"{existing.name} reconnected.")
            else:
                error = room.seat_for_newcomer(now)
                if error is None:
                    player = Player(token=secrets.token_urlsafe(24), name=name, ws=ws, outbox=outbox)
                    token = player.token
                    room.players[token] = player
                    room.ever_joined = True
                    room.log(f"{name} joined the crew." if room.phase in ("lobby", "finished")
                             else f"{name} joined mid-run.")
            if error is None:
                room.ensure_host()
                room.membership_changed(now, before)
        if error:
            outbox.stop()
            await reject(ws, error, CLOSE_FATAL)
            return
        if replaced is not None:
            await _send(replaced, {"type": "error", "fatal": True,
                                   "message": "This crew seat was opened in another tab."})
            await _close(replaced, CLOSE_REPLACED)
        broadcast(room)

        while True:
            msg = await read_message(ws)
            if msg is None:
                continue
            if msg.get("type") == "ping":
                outbox.message({"type": "pong"})
                continue
            async with room.lock:
                player = room.players.get(token)
                if player is None or player.ws is not ws:
                    break
                emit, error, left = room.handle(player, msg, time.monotonic())
                if emit:
                    room.updated = time.monotonic()
            if error:
                outbox.message({"type": "error", "message": error})
            if emit:
                broadcast(room)
            if left:
                outbox.stop()
                await _close(ws, 1000)
                return
    except WebSocketDisconnect:
        pass
    except (ProtocolError, RuntimeError) as exc:
        log.info("Closing socket in room %s: %s", room.code, exc)
        await _close(ws, 1003)
    except Exception:
        log.exception("Unexpected socket error in room %s", room.code)
        await _close(ws, 1011)
    finally:
        if outbox is not None:
            outbox.stop()
        changed = False
        async with room.lock:
            player = room.players.get(token or "")
            if player is not None and player.ws is ws:
                now = time.monotonic()
                before = room.owners()
                player.ws = None
                if player.outbox:
                    player.outbox.stop()
                    player.outbox = None
                player.offline_since = now
                room.log(f"{player.name} disconnected.")
                room.ensure_host()
                room.membership_changed(now, before)
                changed = True
        if changed:
            broadcast(room)
