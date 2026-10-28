# CONFLUX CORE — Compact Arena & Gameplay-Verified Build

**Version:** compact HUD v3 / gameplay integration-tested (2026-10-28)

## What you get

- **Default cinematic view:** the full-size mechanical reactor chamber closely follows the approved gameplay concept art. The environment is a **pre-rendered original AI-generated image** with live selectable ring overlays, rotation indicators, match highlights, core pulse, and a compact responsive HUD. The background is not a fully realtime 3D asset, and the base image itself does not rotate when a ring is moved.
- **Native 3D view:** tap `3D` in the top bar to switch to the procedural, manipulable WebGL2 arena. This separate view has real 3D model geometry, animated rotors, orbit/zoom camera, and energy effects. It is simpler-looking than the cinematic art. If WebGL2 is unavailable, the accessible Canvas2D compatibility renderer is used.
- **Shared multiplayer gameplay:** the FastAPI/WebSocket server is authoritative. Two to four players use a five-character room code, operate the same four interconnected stations, exchange chat messages, and complete three timed stages.
- **Responsive HUD:** a 46–48px tall, compact room/timer/round/score/player strip (832px total at 1600px desktop width); selectable ring control panel; small player list; expandable chat; bottom status strip. On mobile the four rings remain visible in a dedicated portrait composition.
- **Offline solo showcase:** `CONFLUX_CORE_OFFLINE_FIXED.html` is a separate self-contained practice demo (not the real multiplayer game). It now includes all **three** timed stages, per-round scoring, transitions, and Play Again. All four stations are assigned to the local player. Rebuild it after modifying source with `python scripts/build_demo.py`.

## Run the actual multiplayer game

Requires Python 3.10+.

```bash
cd conflux-core
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000`, enter a callsign, and choose **Create Room**. Invite a friend using the room code or copy button. Two players are required to start. The host presses **Start Reactor**. The `+` and `−` controls turn your selected station and counter-rotate its neighbor. If you own multiple stations, select another station in the arena or use the selector control next to the station name. The `3D` / `ART` button switches presentation modes while retaining the same game state.

### Deployment

`render.yaml` and `Dockerfile` are provided. Deploy to a web host supporting persistent WebSockets. Use **one worker/instance**, because the room state is in-memory and not shared between replicas. A stable, public HTTPS URL has **not** been published; configure deployment and perform a two-device playtest before submitting the contest entry.

## File layout

- `server.py`, `game_logic.py` — multiplayer room state and puzzle rules.
- `static/index.html` — game/landing markup.
- `static/style.css` — compact cinematic and mobile HUD.
- `static/app.js` — WebSocket client, server-authoritative state display, ring selection, chat, optional local demonstration.
- `static/scene.js` — native WebGL2 3D geometry/animation/camera, used only in 3D mode.
- `static/fallback.js` — Canvas2D when WebGL2 is unavailable.
- `static/arena-plate.webp` — desktop clean cinematic arena plate derived from the earlier generated gameplay concept.
- `static/arena-mobile.webp` — mobile-oriented art composition.
- `static/cover.png` — competition key art, not a gameplay screenshot.
- `tests/` — multiplayer and puzzle tests.

## Verification performed in this build

- **8/8 Python unit/server tests pass.** JavaScript syntax checks pass.
- **Live network/WebSocket integration check:** two independent real WebSocket clients created/joined a room; start synchronized; movement ownership enforced; chat synchronized; all three rounds solved and scores agreed; Play Again reset to round 1. Result: **PASS**. Source: `scripts/check_multiplayer.py`, run against a locally launched uvicorn server.
- **Reconnect test:** an operator disconnected during play; remaining player saw a paused clock; reconnecting with the same private token restored identity and countdown. Result: **PASS**.
- **Offline Chromium browser tests (via embedded HTML injection):** tested 1600×900, 1024×768, 390×844, and 350×760; no page exceptions or horizontal overflow; controls changed state; chat opened/closed. Result: **PASS**.
- **Offline three-round UI playthrough:** ring hotspots selected, on-screen +/− controls solved all three stages, scores increased, Play Again reset score and round; no JS errors. Result: **PASS**.
- **Compact HUD screenshot measurements:** top strip 832px wide and 48px tall at desktop 1600×900; 698px at 1024×768; mobile width 378px at a 390px viewport.

### Not yet tested / required before contest submission

1. WebGL2 GPU view on your target devices (test renderer, camera, and FPS). This browser environment restricts direct localhost/file navigation and WebGL, so the native GPU appearance isn't verified here.
2. A browser-to-browser live WebSocket test on separate physical devices/networks (the protocol itself **was** exercised by two independent client processes).
3. A public HTTPS deployment with persistent WebSocket connections; no published game URL currently exists.
4. Human playtesting for puzzle difficulty, onboarding, mobile controls, readability and enjoyment.

To repeat the server integration after starting uvicorn locally:

```bash
pip install httpx websockets
python scripts/check_multiplayer.py
```

## Important design limitation

This is a **hybrid visual build**, not a frame-for-frame photorealistic real-time 3D reproduction of the concept image. Cinematic mode accurately reuses the image's environment but does not generate every mechanical detail as a moving 3D mesh. Native 3D mode is genuine GPU geometry, with substantially simpler fidelity. Achieving that exact cinematic fidelity as *fully dynamic 3D* requires original production-grade models, textures, materials, lighting, particle systems, and additional art/optimization work.

## First-time launch and chamber errors

Read `START_HERE.md` for Mac/Windows commands, offline demo, network play and troubleshooting. The standalone demo now enters solo practice regardless of how its HTML is served, and the real multiplayer frontend gives a clearer error if its room API is unavailable.
