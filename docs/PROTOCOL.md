# HTTP & WebSocket Protocol (v2)

Messages are JSON text frames. The server is authoritative; client messages are requests. Every snapshot carries `protocol: 2` and the server `version`.

## HTTP

| Method | Path | Response |
|---|---|---|
| GET | `/` | Game client (HTML, `Cache-Control: no-cache`, assets versioned `?v=`) |
| GET | `/health` | `{"ok":true,"version":"4.0.0","rooms":N,"players_online":N}` |
| POST | `/api/rooms` | `{"code":"ABCDE"}` · `429` if this IP created too many rooms · `503` at capacity |
| GET | `/static/*`, `/favicon.ico` | Assets |

## WebSocket `/ws/{CODE}`

1. Connect, then send within 10 s: `{"type":"join","name":"Nova","token":"<saved session or empty>"}`
2. Receive `state` snapshots; save `session` (per tab, `sessionStorage`) to rejoin the same seat later.

A known `token` reclaims that seat (an older tab holding it is closed with 4001). Otherwise a new seat is created if one is free; offline players' seats are reclaimed (immediately in lobby/finished, after 20 s mid-run). Late joiners enter running games.

### Client → server

| Message | Who / when | Effect |
|---|---|---|
| `{"type":"start"}` | host, lobby or finished, ≥1 human online | New run (score/history/chat reset), round 1 |
| `{"type":"move","dial":0-3,"direction":-1\|1}` | owner of `dial`, playing, not paused | Rotates `dial` and counter-rotates `(dial+1)%4`. Burst 6, 8/s |
| `{"type":"hint"}` | anyone, playing | Logs one optimal move (prefers the requester's station), `hints += 1`, costs 75 pts. Every 4 s |
| `{"type":"chat","message":"…"}` | anyone | ≤180 chars, control/bidi characters stripped. 2/s |
| `{"type":"add_bot"}` | host, lobby or finished | Adds an AI crewmate if a seat is free |
| `{"type":"remove_bot","id":"<public id>"}` | host, lobby or finished | Removes that AI crewmate |
| `{"type":"leave"}` | anyone | Frees the seat immediately, closes the socket |
| `{"type":"ping"}` | anyone | Server replies `{"type":"pong"}` (client sends every 20 s) |

Unknown or malformed messages are ignored. Messages over 2 KB or binary frames close the socket (1003).

### Server → client

**`state`** (sent after every change, and every 0.5 s while a timer runs):

```json
{
  "type": "state", "protocol": 2, "version": "4.0.0", "code": "ABCDE",
  "phase": "lobby|playing|intermission|finished",
  "you": "public id", "session": "your private rejoin token", "host": "public id",
  "revision": 42,
  "players": [{"id": "…", "name": "Nova", "online": true, "bot": false, "is_host": true}],
  "max_players": 4,
  "owners": ["id", "id", "id", "id"],
  "stations": ["AETHER", "EMBER", "PULSE", "PRISM"],
  "symbols": ["✦", "◆", "⬢", "✳", "◈", "●"],
  "target": [1, 2, 3, 4], "positions": [2, 1, 5, 4],
  "stage": 1, "stages": 3, "seconds": 73.5, "duration": 90, "paused": false,
  "score": 0, "last_score": 0, "moves": 5, "par": 3, "hints": 0, "hint_penalty": 75,
  "result": "solved|expired|",
  "history": [{"stage": 1, "result": "solved", "points": 1266, "moves": 3, "par": 3, "hints": 0, "seconds_left": 82}],
  "last_action": {"by": "public id", "dial": 1, "direction": 1, "revision": 41},
  "chat": [{"id": "…", "name": "SYSTEM", "message": "…", "kind": "system|player|bot|hint"}]
}
```

`revision` increases on every meaningful change (including chat), and clients redraw lists only when it changes. `session` is `null` for anyone but the owner; other players' tokens never appear.

**`error`**: `{"type":"error","message":"…"}` for a rejected request (e.g. moving a teammate's station). With `"fatal": true` the socket is about to close and the client returns to the landing page instead of reconnecting.

### Close codes

| Code | Meaning | Client behaviour |
|---|---|---|
| 4004 | Room not found / expired | Back to landing, message shown |
| 4000 | Join refused (room full, bad join) | Back to landing, message shown |
| 4001 | Seat opened in another tab | Back to landing |
| 1008 | Origin not allowed | Back to landing |
| 1003 / 1011 / other | Protocol violation or network failure | Automatic reconnect with backoff (up to 40 tries; *Retry* button after) |

## Invariants

1. The browser never supplies positions, targets, scores or time.
2. Ownership and phase are checked on the server for every move.
3. Moves commute, so the crew may execute an optimal plan in any order.
4. One process owns all rooms: deploy one worker and one instance.
