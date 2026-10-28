"""Room-based realtime multiplayer server for CONFLUX CORE.

Run: uvicorn server:app --host 0.0.0.0 --port 8000
Single-process state for small contest traffic; use one worker/instance.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import os
import random
import re
import secrets
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game_logic import Puzzle, SYMBOLS, N_DIALS, N_STAGES, STAGE_SECONDS

ROOT = os.path.dirname(__file__)
ROOM_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_MAX = 4
ROOM_IDLE_TTL = 3 * 60 * 60
ROOMS: dict[str, 'Room'] = {}


@dataclass
class Player:
    token: str
    name: str
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    ws: WebSocket | None = None
    joined: float = field(default_factory=time.monotonic)
    last_move: float = 0.0
    last_chat: float = 0.0


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
    chat: list[dict[str, Any]] = field(default_factory=list)
    updated: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def active(self) -> list[Player]:
        return [p for p in self.players.values() if p.ws is not None]

    def owners(self) -> list[str | None]:
        available = [p.id for p in self.active()]
        return [available[i % len(available)] if available else None for i in range(N_DIALS)]

    def snapshot(self, token: str | None = None) -> dict[str, Any]:
        now = time.monotonic()
        owners = self.owners()
        if self.phase == "playing":
            remaining = self.remaining if self.paused else max(0, self.end_at - now)
        elif self.phase == "intermission":
            remaining = max(0, self.next_at - now)
        else:
            remaining = 0
        puzzle = self.puzzle
        return {
            "type": "state", "code": self.code, "phase": self.phase,
            "you": self.players[token].id if token in self.players else None,
            "session": token,
            "host": self.players[self.host].id if self.host in self.players else None, "revision": self.revision,
            "players": [
                {"id": p.id, "name": p.name, "online": p.ws is not None,
                 "is_host": p.token == self.host} for p in self.players.values()
            ],
            "owners": owners,
            "target": puzzle.target if puzzle else None,
            "positions": puzzle.positions if puzzle else None,
            "stage": puzzle.stage if puzzle else 0,
            "stages": N_STAGES,
            "seconds": round(remaining, 1), "paused": self.paused,
            "score": self.total_score, "last_score": self.last_score,
            "moves": puzzle.moves if puzzle else 0,
            "result": self.stage_result,
            "symbols": SYMBOLS,
            "chat": self.chat[-25:],
        }

    def log(self, message: str, speaker: str = "SYSTEM") -> None:
        self.chat.append({"name": speaker, "message": message,
                          "id": secrets.token_hex(4)})
        self.chat = self.chat[-25:]
        self.updated = time.monotonic()

    def begin_stage(self, stage: int) -> None:
        self.puzzle = Puzzle.new(stage)
        self.phase = "playing"
        self.remaining = STAGE_SECONDS[stage - 1]
        self.end_at = time.monotonic() + self.remaining
        self.paused = len(self.active()) < 2
        self.stage_result = ""
        self.revision += 1
        self.log(f"Round {stage} is live. Stabilize the four reactors!")

    def finish_stage(self, won: bool) -> None:
        assert self.puzzle is not None
        remaining = max(0, self.end_at - time.monotonic()) if not self.paused else self.remaining
        self.last_score = (150 + int(remaining) * 12 + max(0, 40 - self.puzzle.moves) * 3) if won else 0
        self.total_score += self.last_score
        self.stage_result = "solved" if won else "expired"
        self.log((f"Core stabilized! +{self.last_score} points." if won
                  else "Time expired. The core lost coherence."))
        if self.puzzle.stage >= N_STAGES:
            self.phase = "finished"
        else:
            self.phase = "intermission"
            self.next_at = time.monotonic() + 5
        self.revision += 1


async def broadcast(room: Room) -> None:
    for player in list(room.active()):
        try:
            assert player.ws is not None
            await player.ws.send_json(room.snapshot(player.token))
        except Exception:
            player.ws = None


async def ticker() -> None:
    while True:
        await asyncio.sleep(0.5)
        now = time.monotonic()
        for code, room in list(ROOMS.items()):
            if now - room.updated > ROOM_IDLE_TTL:
                del ROOMS[code]
                continue
            should_emit = False
            async with room.lock:
                if room.phase == "playing" and not room.paused and now >= room.end_at:
                    room.finish_stage(False)
                    should_emit = True
                elif room.phase == "intermission" and now >= room.next_at:
                    assert room.puzzle
                    room.begin_stage(room.puzzle.stage + 1)
                    should_emit = True
                elif room.phase in ("playing", "intermission"):
                    should_emit = True
            if should_emit:
                await broadcast(room)


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


app = FastAPI(title="CONFLUX CORE", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")


class CreateResponse(BaseModel):
    code: str


@app.get("/")
async def index():
    return FileResponse(os.path.join(ROOT, "static", "index.html"))


@app.get("/health")
async def health():
    return {"ok": True, "rooms": len(ROOMS)}


@app.post("/api/rooms", response_model=CreateResponse)
async def create_room():
    for _ in range(10):
        code = "".join(secrets.choice(ROOM_CHARS) for _ in range(5))
        if code not in ROOMS:
            ROOMS[code] = Room(code=code)
            return CreateResponse(code=code)
    raise HTTPException(status_code=503, detail="Could not allocate room")


@app.websocket("/ws/{code}")
async def room_socket(ws: WebSocket, code: str):
    code = code.upper()
    await ws.accept()
    room = ROOMS.get(code)
    if room is None:
        await ws.send_json({"type": "error", "message": "Room not found. Check your code."})
        await ws.close(code=1008)
        return

    token: str | None = None
    try:
        message = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if message.get("type") != "join":
            await ws.send_json({"type": "error", "message": "Join the room first."})
            return
        name = re.sub(r"[\x00-\x1f<>]", "", str(message.get("name", "Player"))).strip()[:18] or "Player"
        requested = str(message.get("token", ""))[:64]
        async with room.lock:
            if requested in room.players:
                token = requested
                player = room.players[token]
                if player.ws is not None and player.ws is not ws:
                    await player.ws.close(code=4001)
                player.ws = ws
            else:
                if room.phase != "lobby":
                    await ws.send_json({"type": "error", "message": "This round has started. Join the next room."})
                    return
                if len(room.players) >= ROOM_MAX:
                    await ws.send_json({"type": "error", "message": "Room is full (4 players)."})
                    return
                token = secrets.token_urlsafe(24)
                player = Player(token=token, name=name, ws=ws)
                room.players[token] = player
                if room.host is None:
                    room.host = token
                room.log(f"{name} joined the crew.")
            room.updated = time.monotonic()
            if room.phase == "playing" and room.paused and len(room.active()) >= 2:
                room.paused = False
                room.end_at = time.monotonic() + room.remaining
                room.log("Connection restored. Countdown resumed.")
            room.revision += 1
        await broadcast(room)

        while True:
            msg = await ws.receive_json()
            action = msg.get("type")
            should_emit = False
            async with room.lock:
                player = room.players.get(token)
                if player is None or player.ws is not ws:
                    break
                now = time.monotonic()
                room.updated = now
                if action == "start" and token == room.host and room.phase in ("lobby", "finished"):
                    if len(room.active()) >= 2:
                        room.total_score = 0
                        room.last_score = 0
                        room.chat.clear()
                        room.begin_stage(1)
                        should_emit = True
                    else:
                        await ws.send_json({"type": "error", "message": "Need at least 2 connected players."})
                elif action == "move" and room.phase == "playing" and not room.paused and room.puzzle:
                    dial = msg.get("dial")
                    direction = msg.get("direction")
                    if type(dial) is int and type(direction) is int and 0 <= dial < N_DIALS and direction in (-1, 1):
                        if room.owners()[dial] == player.id and now - player.last_move >= .12:
                            player.last_move = now
                            if room.puzzle.move(dial, direction):
                                room.finish_stage(True)
                            room.revision += 1
                            should_emit = True
                elif action == "chat":
                    content = re.sub(r"[\x00-\x1f<>]", "", str(msg.get("message", ""))).strip()[:180]
                    if content and now - player.last_chat >= .5:
                        player.last_chat = now
                        room.log(content, player.name)
                        should_emit = True
            if should_emit:
                await broadcast(room)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except (ValueError, KeyError, TypeError):
        pass
    finally:
        if token and token in room.players:
            async with room.lock:
                if room.players[token].ws is ws:
                    room.players[token].ws = None
                    room.log(f"{room.players[token].name} disconnected.")
                    if room.host == token:
                        present = room.active()
                        room.host = present[0].token if present else token
                    if room.phase == "playing" and not room.paused and len(room.active()) < 2:
                        room.remaining = max(0, room.end_at - time.monotonic())
                        room.paused = True
                        room.log("Waiting for a second player. Clock paused.")
                    room.revision += 1
            await broadcast(room)
