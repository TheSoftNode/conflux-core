# Deployment & Operations

Goal: one public **HTTPS** URL where anyone can create a room, invite friends and play, with no install or login.

## Hard requirements

- WebSockets must be supported (the browser connects to `wss://<host>/ws/<CODE>`).
- **Exactly one instance and one Uvicorn worker.** Rooms live in process memory; a second instance would split players into different worlds.
- Restarts and redeploys end all live rooms. Don't redeploy while judges may be playing.

## Option A — Render (config included)

1. Create a GitHub repository whose root is **this `conflux-core` folder** (where `server.py` is).
2. In Render: **New → Blueprint**, select the repo. It reads `render.yaml`:
   - build `pip install -r requirements.txt`
   - start `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1 --ws-max-size 65536 --proxy-headers --forwarded-allow-ips '*'`
   - health check `/health`, `numInstances: 1`
3. **Plan:** `render.yaml` defaults to `free`, which sleeps after ~15 idle minutes; the next visitor then waits 30–60 s and sees a blank page meanwhile. For the judging period, switching to an always-on paid plan (e.g. *Starter*) is strongly recommended. This is a cost decision for the account owner.
4. Deploy, then verify (below).

## Option B — any Docker host (Fly.io, Railway, Cloud Run with min-instances=1 and max=1, a VPS…)

```bash
docker build -t conflux-core .
docker run --rm -p 8000:8000 -e PORT=8000 conflux-core
```

The image runs as a non-root user, has a `HEALTHCHECK`, and starts one worker. `Procfile` is included for Procfile-based hosts (Railway, Heroku-style).

## Verify a deployment (do this every time)

```bash
curl https://<host>/health                          # {"ok":true,"version":"4.0.1",...}
python scripts/check_multiplayer.py https://<host>  # must end: ALL CHECKS PASSED
```

Then by hand: open the URL on a laptop **and** a phone on mobile data (different networks), create a room on one, join from the other via the invite link, play a round, chat, refresh one device mid-round (it should rejoin the same seat), and try *Quick Play*. In DevTools → Network → WS you should see a `101` upgrade to `wss://`.

## Configuration (environment variables, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | 8000 | Port to listen on (set by most hosts) |
| `CONFLUX_ALLOWED_ORIGINS` | *(any)* | Comma-separated origins allowed to open WebSockets, e.g. `https://conflux.example.com`. Set this once your final domain is known. |
| `CONFLUX_CREATE_LIMIT` | 15 | Rooms one IP may create per minute |
| `CONFLUX_MAX_ROOMS` | 500 | Global cap on simultaneous rooms |

No secrets, API keys or databases are needed.

## Built-in protections

- Room creation rate-limited per IP, global room cap, 5-character codes without look-alike characters.
- WebSocket: 10 s join deadline, 2 KB message cap (64 KB frame cap at the server), binary frames rejected, malformed JSON ignored, moves token-bucket limited (burst 6, 8/s), chat 2/s, hints every 4 s.
- Server-authoritative state: clients can't set positions, targets, scores or timers; ownership is checked on every move.
- Private rejoin tokens are only ever sent to their owner.
- Each connection has its own outbox that always sends the newest snapshot, so a slow phone can't delay anyone else.
- Security headers on every response (CSP `script-src 'self'`, `nosniff`, referrer policy). Static assets are cache-busted by version.
- Rooms expire automatically: unused after 10 min, abandoned (no humans) after 20 min, idle after 3 h.

## Capacity

Measured locally (`scripts/load_test.py`, 2026-10-29): **100 simultaneous rooms / 200 sockets, 2,000 moves, median move→broadcast 2 ms, p95 30 ms, 0 failures.** That is far above contest traffic for a single small instance.

## Monitoring

`GET /health` returns `ok`, `version`, `rooms` and `players_online`. Point an uptime monitor at it (this also keeps free-tier hosts awake, but check your host's terms). Server logs record unexpected socket errors with the room code. Tokens and chat are not logged.
