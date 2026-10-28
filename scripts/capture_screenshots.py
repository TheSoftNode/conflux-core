"""Capture real gameplay screenshots (two live browser players) into docs/screenshots.

  python scripts/capture_screenshots.py [base-url]
Needs a running server and Playwright with Chrome/Chromium.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_logic import solve  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765'
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)


def state(pg):
    return pg.evaluate('window.ConfluxDebug.state')


def wait(pg, js, timeout=20000):
    pg.wait_for_function(f'(()=>{{const s=window.ConfluxDebug.state;return !!s&&({js})}})()', timeout=timeout)


def page(browser, vp, name):
    ctx = browser.new_context(viewport=vp, bypass_csp=True, device_scale_factor=1)
    ctx.add_init_script("localStorage.setItem('conflux-help-seen','1');localStorage.setItem('conflux-sound','off')")
    pg = ctx.new_page()
    pg.goto(BASE)
    pg.fill('#player-name', name)
    return pg


def move_once(players):
    s = state(players[0])
    if s['phase'] != 'playing':
        return False
    plan = solve(s['positions'], s['target'])
    dial, direction = plan[0]
    actor = next(p for p in players if state(p)['you'] == s['owners'][dial])
    actor.click(f".ring-chip[data-dial='{dial}']")
    actor.click('#rotate-right' if direction > 0 else '#rotate-left')
    actor.wait_for_timeout(350)
    return True


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome', headless=True)
    for label, vp in (('desktop', {'width': 1600, 'height': 900}), ('mobile', {'width': 390, 'height': 844})):
        host = page(browser, vp, 'Nova')
        host.screenshot(path=OUT / f'{label}-1-landing.png')
        host.click('#create-room')
        wait(host, "s.phase==='lobby'")
        code = state(host)['code']
        guest = page(browser, {'width': 1280, 'height': 800}, 'Orion')
        guest.goto(f'{BASE}/?room={code}')
        guest.fill('#player-name', 'Orion')
        guest.click('#join-room')
        wait(host, 's.players.length===2')
        host.wait_for_timeout(300)
        host.screenshot(path=OUT / f'{label}-2-lobby.png')
        host.click('#start-button')
        wait(host, "s.phase==='playing'")
        guest.click('#toggle-comms')
        guest.fill('#chat-input', 'I have Ember + Prism. Turning Ember first!')
        guest.press('#chat-input', 'Enter')
        move_once([host, guest])
        host.wait_for_timeout(500)
        host.screenshot(path=OUT / f'{label}-3-gameplay.png')
        while move_once([host, guest]):
            pass
        wait(host, "s.phase==='intermission'")
        host.wait_for_timeout(500)
        host.screenshot(path=OUT / f'{label}-4-round-result.png')
        if label == 'desktop':
            host.click('[data-close-result]')
            host.click('#open-help')
            host.wait_for_timeout(300)
            host.screenshot(path=OUT / 'desktop-5-how-to-play.png')
            host.click('#help-ok')
            for stage in (2, 3):
                wait(host, f"s.phase==='playing'&&s.stage==={stage}")
                while move_once([host, guest]):
                    pass
            wait(host, "s.phase==='finished'")
            host.wait_for_timeout(500)
            host.screenshot(path=OUT / 'desktop-6-final-summary.png')
            host.click('[data-close-result]')
            host.click('#toggle-view')
            host.wait_for_timeout(1500)
            host.screenshot(path=OUT / 'desktop-7-native-3d.png')
        host.context.close()
        guest.context.close()
    browser.close()
print('saved to', OUT)
