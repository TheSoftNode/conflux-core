# Current Status — v4.0.0 (2026-10-29)

## Verified

| Area | Status | Evidence |
|---|---|---|
| Puzzle rules, optimal solver, escalating rounds | ✅ | Brute-force-checked over every reachable state (`tests/test_game.py`) |
| Rooms, join/rejoin, host handover, late join, leave, seat reclaim | ✅ | `tests/test_room.py`, `tests/test_server.py`, browser E2E |
| Solo play and AI crewmates | ✅ | Unit, socket and browser tests; live check |
| Three timed rounds, intermission, scoring, replay | ✅ | Unit + live `check_multiplayer.py` |
| Abuse limits, malformed input, security headers | ✅ | `tests/test_server.py` |
| Concurrency | ✅ | 100 rooms / 200 sockets, p95 30 ms (`scripts/load_test.py`) |
| Browser multiplayer (two real browsers) | ✅ | Chrome E2E; WebKit host + Firefox guest (`cross_browser_smoke.py`) |
| Safari engine (WebKit) / iPhone-sized touch | ✅ (engine) | WebKit 18 via Playwright; **real iPhone still to try** |
| Responsive layout | ✅ | 9 viewports 350×700 → 1920×1080, automated |
| 3D view on a real GPU | ✅ | Firefox on Intel Iris 6100; context-loss recovery test |
| GPU-less machines | ✅ | Automatic 2D renderer + low-power mode, 56–60 fps |
| Offline practice file | ✅ | `CONFLUX_CORE_OFFLINE_FIXED.html`, E2E-tested |

## Remaining before submission (need you, not code)

1. **Deploy** to a public HTTPS host (`docs/DEPLOYMENT.md`), ideally on an always-on plan, then run `python scripts/check_multiplayer.py https://<host>`.
2. **Two-network human test** on the public URL: laptop + phone on mobile data, full run, refresh mid-round.
3. **Real phones:** one iPhone (Safari) and one Android (Chrome).
4. **One first-time player** tries it without help. Watch where they hesitate.
5. Set `CONFLUX_ALLOWED_ORIGINS` to the final domain (optional hardening).
6. **Eligibility and rules:** confirm residency/presence in an eligible country, and that the mission accepts this project as "built with OpenAI" (see rules p. 1). Submit title, cover, description and the live URL before **2026-10-30 11:59 PM PT**.

## Known limitations (by design)

- Rooms live in one process's memory: a restart or redeploy ends live games. Deploy one instance.
- The cinematic view is pre-rendered art with live overlays; the painted rings don't physically rotate. The 3D view is real-time but simpler than the art.
- Rejoin works per browser tab (`sessionStorage`); a different device joins as a new player.
- No accounts, leaderboards or persistence.
