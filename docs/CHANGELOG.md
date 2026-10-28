# Changelog

## 4.0.0 — 2026-10-29

### Fixed (bugs in the supplied build)
- **Ghost lobby seats:** players who left a lobby kept their seat forever, so a room could become permanently "full". Offline seats are now reclaimed, explicit *Exit* frees the seat, and stale players are pruned.
- **Reconnect loop on rejected joins:** "room full" / "already started" closed with an abnormal code, so the client retried about 12 times over ~45 s while showing error popups. Rejections are now marked fatal with dedicated close codes, and the client returns to the landing page.
- **Malformed WebSocket messages** (`[]`, non-JSON, binary, oversized) raised uncaught errors. All are now handled.
- **Chat never appeared for other players** until something else changed (the state revision wasn't bumped).
- **Names/chat:** tabs and newlines were deleted rather than turned into spaces; bidi-override characters are now stripped.
- **3D view went blank permanently** when the browser dropped the WebGL context. It now rebuilds itself, and uses the 2D renderer if the GPU keeps failing.
- **3D froze the page on GPU-less machines** (0 fps). Software rasterisers are now detected and the optimized 2D renderer is used. The 2D renderer itself went from 6 to 56 fps (no canvas shadows, cached backdrop, 30 fps cap).
- **WebKit/Safari** threw an error drawing a zero-size canvas.
- **Mobile:** 3D button pushed off-screen at 350–430 px; ring banner overlapping the controls; hint button too small to tap.
- A slow client could stall every room's timers (the ticker awaited each send). Each connection now has its own non-blocking, conflating outbox.
- Ring stations were linked diagonally on screen (TL→TR→BL→BR). The order is now clockwise around the arena.

### Added
- **Solo play and AI crewmates** (host adds up to 3; *Quick Play* = you + AI in one click). AI plays its own stations optimally at a human pace and nudges you in chat.
- **Live symbols on every ring** in the art view (current + target), ring status chips for all four stations, "LINKED" highlight on the station your move affects, floating teammate-move notes.
- **Lobby panel** (big code, copy/share invite, seats, add/remove AI), **round result** and **final summary** with par, rank and copyable result; **How to play** card on first visit.
- **Par** (optimal moves, from a proven-optimal solver), escalating difficulty per round, efficiency scoring, **hints** with a penalty.
- Mid-run joining, automatic rejoin after refresh, host handover, pause only when all humans leave, reconnect banner with retry, keepalive pings.
- Sound effects (toggle, remembered), keyboard shortcuts, timer bar, urgent countdown.
- Server: rate limits, room cap, message size limits, room expiry, crash-proof ticker, CSP and security headers, cache-busted assets, `/health` with version.
- Deploy: hardened Dockerfile (non-root, healthcheck), `Procfile`, one-instance `render.yaml`.
- Tooling: deployable live check, load test, cross-browser smoke, screenshot capture.
- Tests: 8 → **111**, including brute-force solver proof, JS/Python parity and real-browser E2E.

## 3.x — before 2026-10-28
Original compact cinematic HUD build (see `docs/screenshots/archive-v3`).
