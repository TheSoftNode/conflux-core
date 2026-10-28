# CONFLUX CORE — Verification and Deployment Checklist

## Verified on 2026-10-28

- [x] 8 existing Python tests pass
- [x] JS syntax passes
- [x] Compact desktop HUD at 1600×900 and 1024×768
- [x] Compact responsive HUD at 390×844 and 350×760 without horizontal overflow
- [x] Offline Chromium controls, chat toggling and ring selection work
- [x] Offline all 3 rounds completed by selecting ring hotspots and clicking +/− controls; replay resets score
- [x] Live protocol: 2 WebSocket clients join, start, rotate, finish 3 rounds, synchronize score and replay
- [x] Server rejects unauthorized ring moves
- [x] Player disconnect pauses timer; reconnect with session restores identity and resumes countdown

## Remaining release gates

- [ ] Deploy as single worker/instance to HTTPS host with WebSocket support
- [ ] Two-player browser test on different devices and networks
- [ ] Native WebGL2 view on hardware: check for shader compile failures, jitter, frame rate
- [ ] First-time human players can learn the mechanics and complete the game without developer intervention
- [ ] Stress-test repeat joins, shared codes, disconnects, game completion on mobile
- [ ] Capture actual browser gameplay video and final high-resolution screenshots
- [ ] Enter submission details on Handshake before the explicit rules deadline

## Commands

```bash
cd conflux-core
pip install -r requirements.txt
python -m pytest -q
uvicorn server:app --host 127.0.0.1 --port 8765 --workers 1
# separate terminal:
pip install httpx websockets
python scripts/check_multiplayer.py
# rebuild solo HTML after changing source:
python scripts/build_demo.py
```

The cinematic environment is a pre-rendered image with live interactive overlays. Native mode is a separate procedural WebGL2 renderer; photorealistic artwork is not full realtime 3D.
