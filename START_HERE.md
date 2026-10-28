# CONFLUX CORE — Start Here

## Just want to try it? (no setup)
Open **`CONFLUX_CORE_OFFLINE_FIXED.html`** (one folder up) in Chrome, Firefox or Safari. It's solo practice: you control all four stations. Online rooms and AI crewmates need the server.

## Full game on your computer
Needs Python 3.10+.

**Mac / Linux**
```sh
cd conflux-core
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
```
**Windows PowerShell**
```powershell
cd path\to\conflux-core
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
```
Open **http://127.0.0.1:8000**, type a callsign, then:
- **Create Room** → share the code or invite link → **Start**, or
- **Quick Play** → you + an AI crewmate, starts immediately.

Second device on the same Wi-Fi: start with `--host 0.0.0.0` and open `http://<computer's LAN IP>:8000` on the phone.

## For the contest
The judges need a **public HTTPS URL**. Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), then check [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) and [SUBMISSION_COPY.md](SUBMISSION_COPY.md).

## Troubleshooting
- **"Cannot reach the game server"**: the Python server isn't running, or you opened `static/index.html` directly. Use the URL above.
- **"Room not found"**: rooms vanish when the server restarts; both players must use the same server.
- **"Room is full"**: four crew already (AI crewmates count). The host can remove an AI crewmate between runs.
- **3D view looks flat/2D**: your browser has no GPU acceleration, so the game automatically uses the fast 2D renderer.
- **No sound**: tap anywhere first (browsers require a gesture), and check the ♪ button.
