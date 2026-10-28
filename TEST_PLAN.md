# Test Plan

The full test inventory, commands and recorded results are in **[docs/TESTING.md](docs/TESTING.md)**.

Quick commands:
```bash
python -m pytest                               # 111 automated tests (unit, protocol, parity, browser E2E)
python scripts/check_multiplayer.py [URL]      # live end-to-end game against a running/deployed server
```

Manual release checks (after deploying):
- [ ] Laptop + phone on **different networks** finish a full 3-round run on the public URL
- [ ] Refresh one device mid-round → it rejoins the same seat
- [ ] Real iPhone (Safari) and Android (Chrome): tap, rotate, chat, sound
- [ ] Quick Play from a fresh incognito window
- [ ] A first-time player finishes round 1 using only the in-game help
