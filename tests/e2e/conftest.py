"""Real-browser fixtures: a live uvicorn server and Chrome/Chromium via Playwright."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port),
                             "--workers", "1", "--log-level", "warning"], cwd=ROOT,
                            env={**os.environ, "CONFLUX_CREATE_LIMIT": "1000"})
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            try:
                b = p.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No Chromium available: {exc}")
        yield b
        b.close()


class Player:
    """One browser context (its own sessionStorage = one crew member)."""

    def __init__(self, browser, base_url, viewport=None, touch=False):
        self.ctx = browser.new_context(viewport=viewport or {"width": 1440, "height": 900}, has_touch=touch,
                                       bypass_csp=True)  # lets the test harness poll page state
        self.ctx.add_init_script("localStorage.setItem('conflux-help-seen','1'); localStorage.setItem('conflux-sound','off');")
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.base = base_url

    def state(self):
        return self.page.evaluate("window.ConfluxDebug.state")

    def wait(self, js_predicate, timeout=10000):
        self.page.wait_for_function(f"(() => {{ const s = window.ConfluxDebug.state; return !!s && ({js_predicate}); }})()",
                                    timeout=timeout)
        return self.state()

    def create(self, name, quick=False):
        self.page.goto(self.base)
        self.page.fill("#player-name", name)
        self.page.click("#quick-play" if quick else "#create-room")
        return self.wait("s.phase === 'lobby' || s.phase === 'playing'")

    def join(self, code, name):
        self.page.goto(f"{self.base}/?room={code}")
        self.page.fill("#player-name", name)
        self.page.click("#join-room")
        return self.wait("s.you")

    def move(self, dial, direction):
        self.page.click(f".ring-chip[data-dial='{dial}']")
        self.page.click("#rotate-right" if direction > 0 else "#rotate-left")

    def close(self):
        self.ctx.close()


@pytest.fixture
def make_player(browser, base_url):
    made = []

    def factory(**kwargs):
        p = Player(browser, base_url, **kwargs)
        made.append(p)
        return p

    yield factory
    errors = [e for p in made for e in p.errors]
    for p in made:
        p.close()
    assert not errors, f"browser errors: {errors}"
