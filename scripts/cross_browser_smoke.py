"""Cross-engine smoke test: Safari's WebKit, Firefox and Chrome playing together.

  python scripts/cross_browser_smoke.py [base-url]

Needs a running server and Playwright with webkit/firefox/chromium installed
(on macOS 13, use playwright==1.47 — newer releases dropped those builds).
Checks per engine: page loads without JS errors, quick play with an AI crewmate
solves a round, 3D toggle works; then a WebKit host and Firefox guest share a room,
chat, and solve a round together; finally an iPhone-sized WebKit touch session.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_logic import solve  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765').rstrip('/')
INIT = "localStorage.setItem('conflux-help-seen','1');localStorage.setItem('conflux-sound','off');"
failures = []


def check(cond, msg):
    print(('PASS: ' if cond else 'FAIL: ') + msg)
    if not cond:
        failures.append(msg)


def open_page(browser, **ctx):
    c = browser.new_context(**ctx)
    c.add_init_script(INIT)
    pg = c.new_page()
    pg.errors = []
    pg.on('pageerror', lambda e: pg.errors.append(str(e)))
    return pg


def st(pg):
    return pg.evaluate('window.ConfluxDebug.state')


def wait(pg, predicate, timeout=20.0):
    """Poll from Python: WebKit enforces the game's strict CSP even for test tooling."""
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = st(pg)
        if s and predicate(s):
            return s
        pg.wait_for_timeout(100)
    raise AssertionError('timed out waiting for game state')


def play_mine(pages, stage):
    for _ in range(80):
        s = st(pages[0])
        if s['phase'] != 'playing':
            break
        plan = solve(s['positions'], s['target'])
        acted = False
        for pg in pages:
            me = st(pg)['you']
            mine = [m for m in plan if s['owners'][m[0]] == me]
            if mine:
                d, dr = mine[0]
                pg.click(f".ring-chip[data-dial='{d}']")
                pg.click('#rotate-right' if dr > 0 else '#rotate-left')
                pg.wait_for_timeout(250)
                acted = True
                break
        if not acted:
            pages[0].wait_for_timeout(400)
    wait(pages[0], lambda s: len(s['history']) >= stage)
    return st(pages[0])['history'][stage - 1]['result']


with sync_playwright() as p:
    engines = {n: getattr(p, n).launch() for n in ('webkit', 'firefox', 'chromium')}
    for name, browser in engines.items():
        pg = open_page(browser, viewport={'width': 1366, 'height': 768})
        pg.goto(BASE)
        check(pg.is_visible('#create-room'), f'{name}: landing renders')
        pg.fill('#player-name', name.title())
        pg.click('#quick-play')
        wait(pg, lambda s: s['phase'] == 'playing')
        check(play_mine([pg], 1) == 'solved', f'{name}: player + AI crewmate solve round 1')
        pg.click('[data-close-result]') if pg.is_visible('[data-close-result]') else None
        pg.click('#toggle-view')
        pg.wait_for_timeout(1200)
        mode = pg.evaluate('window.ConfluxScene && window.ConfluxScene.mode')
        check(mode in ('webgl', 'fallback'), f'{name}: 3D view active ({mode})')
        check(not pg.errors, f'{name}: no JavaScript errors {pg.errors[:2]}')
        pg.context.close()

    host = open_page(engines['webkit'], viewport={'width': 1280, 'height': 800})
    guest = open_page(engines['firefox'], viewport={'width': 1280, 'height': 800})
    host.goto(BASE); host.fill('#player-name', 'Safari'); host.click('#create-room')
    wait(host, lambda s: s['phase'] == 'lobby')
    code = st(host)['code']
    guest.goto(f'{BASE}/?room={code}'); guest.fill('#player-name', 'Firefox'); guest.click('#join-room')
    wait(host, lambda s: len(s['players']) == 2)
    host.click('#start-button')
    wait(guest, lambda s: s['phase'] == 'playing')
    check(st(host)['positions'] == st(guest)['positions'], 'webkit host + firefox guest see identical puzzle')
    guest.click('#toggle-comms'); guest.fill('#chat-input', 'hello from firefox'); guest.press('#chat-input', 'Enter')
    wait(host, lambda s: any(m['message'] == 'hello from firefox' for m in s['chat']))
    check('hello from firefox' in host.text_content('#chat-log'), 'cross-engine chat delivered')
    check(play_mine([host, guest], 1) == 'solved', 'webkit + firefox crew solve round 1 together')
    check(st(host)['score'] == st(guest)['score'] > 0, 'scores identical across engines')
    check(not host.errors and not guest.errors, f'no JS errors in shared room {host.errors[:1]} {guest.errors[:1]}')
    host.context.close(); guest.context.close()

    phone = open_page(engines['webkit'], viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                      device_scale_factor=3,
                      user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
    phone.goto(BASE); phone.fill('#player-name', 'iPhone'); phone.tap('#quick-play')
    wait(phone, lambda s: s['phase'] == 'playing')
    check(phone.evaluate('document.documentElement.scrollWidth') <= 390, 'iPhone WebKit: no horizontal scroll')
    s = st(phone)
    mine = next(i for i in range(4) if s['owners'][i] == s['you'])
    phone.tap(f".ring-hotspot[data-dial='{mine}']")
    phone.tap('#rotate-right')
    wait(phone, lambda s: s['moves'] >= 1 or s['phase'] != 'playing')
    check(True, 'iPhone WebKit: tap select + rotate works')
    phone.screenshot(path=str(Path(__file__).resolve().parents[1] / 'docs' / 'screenshots' / 'iphone-webkit-gameplay.png'))
    check(not phone.errors, f'iPhone WebKit: no JS errors {phone.errors[:2]}')
    for b in engines.values():
        b.close()

print(f"\nCROSS-BROWSER SMOKE: {'ALL PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
