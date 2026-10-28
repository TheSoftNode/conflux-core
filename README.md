# CONFLUX CORE — One Reactor. Four Minds.

A real-time cooperative puzzle for **1–4 players in the browser**. No login, no install. Four linked reactor stations sit clockwise around a collapsing energy core. Every turn you make **pushes the next station the other way**, so the crew has to plan together.

- **Play together:** create a room, share the 5-letter code or invite link, start.
- **Play alone:** *Quick Play* puts you with an AI crewmate (VEGA) who plays its own stations, or you can start solo and control all four.
- **Three rounds**, each harder and shorter (90/80/70 s, optimal solutions of 2–3, 4–5, then 6 moves). Score = speed + efficiency vs **par**; hints cost points.
- Works on phones and laptops: Chrome, Firefox and Safari/WebKit verified.

Version **4.0.0** · Python 3.10+ · FastAPI + WebSockets · plain HTML/CSS/JS (no CDN, no build step).

## Run it locally

```bash
cd conflux-core
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000. To play with a second device on the same Wi-Fi, use `--host 0.0.0.0` and open `http://<your-computer's-LAN-IP>:8000` on the other device.

**Offline practice:** `../CONFLUX_CORE_OFFLINE_FIXED.html` is a single file you can open without a server (solo, all four stations). Rebuild it after editing the client with `python scripts/build_demo.py ../CONFLUX_CORE_OFFLINE_FIXED.html`.

## Deploy (public URL for the contest)

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. In short: push this folder to GitHub, create a Render *Blueprint* from `render.yaml` (or any Docker host with the `Dockerfile`), keep **one instance and one worker**, then verify the deployed site with:

```bash
python scripts/check_multiplayer.py https://<your-app>.onrender.com
```

## How it plays

| | |
|---|---|
| Stations (clockwise) | **AETHER** (cyan, top-left) → **EMBER** (orange, top-right) → **PULSE** (blue, bottom-right) → **PRISM** (magenta, bottom-left) → back to AETHER |
| Move | Turning station *i* by +1 also turns station *i+1* by −1 (mod 6 symbols) |
| Ownership | 1 player: all four · 2: alternate · 3: first player gets two · 4: one each. AI crewmates take seats like players. |
| Win a round | All four current symbols equal their targets before time runs out |
| Points | `150 + 12 × seconds left + max(0, 120 − 15 × moves over par) − 75 × hints`, minimum 50; 0 if time expires |
| Controls | Tap a ring or the ring chips, then − / +. Keyboard: `1`–`4` select, `←`/`→` rotate, `↑`/`↓` cycle your stations, `H` hint, `C` chat, `M` sound, `?` help |
| Views | Default *cinematic* art view with live overlays; `3D` switches to a real-time WebGL2 scene (automatic 2D fallback on machines without GPU acceleration) |

Players can join mid-run, rejoin after a refresh or dropped connection (same tab), and the host role passes on automatically. The clock pauses only if every human disconnects.

## Project layout

```
server.py            FastAPI app: rooms, WebSocket protocol, AI crew, timers, security headers
game_logic.py        Puzzle rules, provably optimal solver, generation, scoring
static/
  index.html         Landing, HUD, lobby, results, help
  app.js             Client: connection/reconnect, rendering, input, offline practice
  logic.js           Same rules as game_logic.py for the browser (parity-tested)
  scene.js           WebGL2 3D renderer (self-healing on context loss)
  fallback.js        Canvas 2D renderer for GPU-less devices
  style.css          Responsive HUD (350 px phones → 1920 px desktops)
scripts/
  check_multiplayer.py   Live HTTP/WebSocket check against local or deployed server
  load_test.py           Many concurrent rooms; reports latency
  cross_browser_smoke.py WebKit + Firefox + Chromium playing together
  capture_screenshots.py Real gameplay screenshots into docs/screenshots
  build_demo.py          Single-file offline practice build
tests/               pytest: logic, room state machine, socket protocol, JS parity, real-browser E2E
docs/                Deployment, testing, protocol, status, changelog, screenshots
```

## Test it

```bash
pip install -r requirements-dev.txt && python -m playwright install chromium
python -m pytest            # 111 tests: unit, protocol, JS parity, real-browser E2E
```

Details, extra tools and the latest recorded results: **[docs/TESTING.md](docs/TESTING.md)**.

## More documentation

- [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md): what's verified, what's left before submission
- [docs/PROTOCOL.md](docs/PROTOCOL.md): HTTP routes and WebSocket messages
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): hosting, configuration, operations
- [docs/TESTING.md](docs/TESTING.md): test suites, tools and evidence
- [docs/CHANGELOG.md](docs/CHANGELOG.md): what changed in v4
- [SUBMISSION_COPY.md](SUBMISSION_COPY.md): contest title, description and checklist

**About the visuals:** the default view is original pre-rendered concept art with live interactive overlays (the painted rings themselves don't move). The `3D` view is genuine real-time geometry, simpler than the artwork.
