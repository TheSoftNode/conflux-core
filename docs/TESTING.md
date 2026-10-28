# Testing

## Automated suite: `python -m pytest`

Setup once: `pip install -r requirements-dev.txt && python -m playwright install chromium` (Chrome, if installed, is used automatically).

| File | What it proves |
|---|---|
| `tests/test_game.py` | Coupling rule; reachable states = the `sum mod 6` class; **solver is optimal for every reachable state** (checked against brute-force BFS); plans work in any order; generated puzzles match each round's par range; scoring |
| `tests/test_room.py` | Room state machine on a controllable clock: 1–4 player ownership, host rules (never a bot), solo 3-round run, timer expiry → intermission → finish, pause only when all humans leave, AI crew plays only its stations and helps finish, hints and penalties, seat reclaim, pruning, leave, chat sanitising/limits, token privacy, restart, room expiry, outbox conflation (slow clients can't stall others) |
| `tests/test_server.py` | Real ASGI app over HTTP/WebSocket: headers and cache busting, rate limits and capacity, fatal errors and close codes, join timeout, malformed/oversized/binary frames, two-player sync, solo 3 rounds + replay, reconnect and tab takeover, disconnect reassignment, pause/resume, late join, leave, AI crew round, hints. Includes regressions for the **ghost lobby seat** and **bot-token hijack** |
| `tests/test_js_parity.py` | `static/logic.js` and `game_logic.py` agree on rotate, solve, scoring and constants across 500 random cases, plus 600 JS-generated puzzles (needs Node) |
| `tests/test_submission.py` | Every element ID used by `app.js` exists; no duplicate IDs; scripts load in order; all assets local (no CDN); offline build fully self-contained; deploy configs use one worker |
| `tests/e2e/test_browser.py` | Real Chrome against a real server: two browsers create/join/chat/solve; Quick Play with AI; refresh rejoins the same seat; bad code and full room return cleanly to the landing page (no retry loop); leaving frees the seat; keyboard + hint; mobile tap play; 3D toggle (correct renderer for the hardware, >20 fps); **WebGL context-loss recovery**; offline practice file; **layout sweep at 9 viewports** (350×700 → 1920×1080: no overlap, nothing off-screen, no horizontal scroll) |

Run only the fast tests with `python -m pytest --ignore=tests/e2e`.

## Tools (need a running server)

```bash
uvicorn server:app --port 8765 --workers 1      # terminal 1
python scripts/check_multiplayer.py [URL]       # full live game: 2 clients, 3 rounds, replay, AI crew
CONFLUX_CREATE_LIMIT=5000 uvicorn server:app --port 8765   # for the load test
python scripts/load_test.py [URL] [rooms]       # concurrency + latency
python scripts/cross_browser_smoke.py [URL]     # WebKit + Firefox + Chromium together
python scripts/capture_screenshots.py [URL]     # real gameplay screenshots → docs/screenshots
```

`cross_browser_smoke.py` needs Playwright's WebKit and Firefox builds. On macOS 13 install them with `playwright==1.47` in a separate venv (newer releases dropped macOS 13).

## Results recorded 2026-10-29 (macOS 13.6, Python 3.12.8, Chrome stable)

- `python -m pytest`: **111 passed** (≈2.5 min including E2E).
- `check_multiplayer.py` against local Uvicorn and against the exact production start command: **ALL CHECKS PASSED**, server log clean.
- `load_test.py 100`: **100 rooms / 200 sockets / 2,000 moves: median 2 ms, p95 30 ms, max 57 ms, 0 failures.**
- `cross_browser_smoke.py`: **all 20 checks passed.** WebKit 18 (Safari engine), Firefox 130 and Chromium each solve a round with an AI crewmate; a WebKit host and Firefox guest share a room, chat and solve together with identical scores; iPhone-sized WebKit touch play with no horizontal scroll. Firefox rendered the 3D view on this Mac's real GPU (Intel Iris 6100) with no errors.
- Rendering on a GPU-less path (Chrome falls back to SwiftShader on this Mac's blocklisted GPU): the art view holds 60 fps; the 3D button automatically uses the optimized 2D renderer (56 fps). Before the fix it was 6 fps, and 0 fps for WebGL.

## Not covered by automation (do by hand after deploying)

- Two humans on **different networks** (laptop on Wi-Fi + phone on mobile data) completing a full run on the public URL.
- A real iPhone (Safari) and a real Android phone: tapping, sound after the first tap, rotation, and backgrounding the tab mid-round, then returning.
- A first-time player who has never seen the game: can they finish round 1 using only the in-game help?
