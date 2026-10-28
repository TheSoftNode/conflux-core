# CONFLUX CORE — How to Run It

**Important:** The game is browser-based. The complete online game needs the Python server; the single-file offline demo does not. Do not open `static/index.html` directly and expect room creation to work.

## Quickest option: play offline (one player)

Open `CONFLUX_CORE_OFFLINE_FIXED.html` in Chrome, Edge, or Firefox. It automatically starts three-round practice and does not create real online rooms. This is the right version for checking mechanics and layout without setup. It is also safe to preview through a local static web server.

## Full multiplayer on your own computer

Requirements: Python 3.10+ and an internet connection to install dependencies.

### Mac / Linux

Unzip the build. Open Terminal and navigate to the extracted `conflux-core` folder (you can type `cd ` and drag the folder into Terminal).

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000** in Chrome or Edge. Enter your callsign, click **Create Room**, and share the five-character code. Invite a second player before pressing Start Reactor. Keep Terminal open while playing; Ctrl+C stops the server.

### Windows PowerShell

Unzip the build and open PowerShell in the extracted `conflux-core` folder.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000** in your browser. Share the room code; two players are required to start.

## Two devices or worldwide players

The default localhost address can only be opened on the same computer. For a second device on the same Wi-Fi network, launch the server with `--host 0.0.0.0` instead and use your computer's local network IP address, e.g. `http://192.168.1.10:8000` (that address is only an example). Check the computer firewall. For worldwide multiplayer and the Handshake contest, deploy the FastAPI app to a **public HTTPS host supporting WebSockets**. This source has a `render.yaml` and `Dockerfile`, but there is **no public deployed URL yet**. Keep one server worker/instance because room state is in memory.

## Troubleshooting

- **Unable to open a chamber**: You opened the full game without its Python backend, or the server is not reachable. Run the server and use `http://127.0.0.1:8000`, or use the offline demo.
- **Page cannot be reached**: Check Terminal for errors and confirm the server started; don't close its window.
- **Room code not found**: Both players must connect to the **same running server**. A different server instance does not share its rooms.
- **Start is disabled**: A second player must join the room.
- **3D graphics look simpler than artwork**: The default cinematic view is pre-rendered environment art with interactive overlays. The switchable native WebGL renderer uses simpler real-time 3D geometry.

## What the contest expects

The mission calls for a live, replayable multiplayer game at a **public URL** that runs in browsers on phones/laptops without a login or app install. A standalone HTML file or localhost is only for testing; it is not the required public project URL.
