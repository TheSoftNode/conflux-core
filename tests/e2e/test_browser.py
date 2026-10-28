"""End-to-end: real Chrome pages talking to a real server over real WebSockets.

Run: python -m pytest tests/e2e -m e2e
"""
import subprocess
import sys
from pathlib import Path

import pytest

from game_logic import rotate, solve

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def owner_page(players, state, dial):
    return next(p for p in players if p.state()["you"] == state["owners"][dial])


def play_own_moves_until_solved(player, stage, timeout_moves=60):
    """Make this player's share of the optimal plan via the UI until the round is solved (AI crew does the rest)."""
    for _ in range(timeout_moves):
        s = player.state()
        if s["phase"] != "playing" or s["stage"] != stage:
            break
        mine = [m for m in solve(s["positions"], s["target"]) if s["owners"][m[0]] == s["you"]]
        if mine:
            dial, direction = mine[0]
            before = s["revision"]
            player.move(dial, direction)
            player.wait(f"s.revision > {before}")
        else:
            player.page.wait_for_timeout(400)
    return player.wait(f"s.history.length >= {stage}", timeout=15000)


def test_two_browsers_create_join_chat_and_solve_a_round(make_player):
    host, guest = make_player(), make_player()
    lobby = host.create("Nova")
    assert lobby["phase"] == "lobby" and host.page.is_visible("#lobby-panel")
    code = lobby["code"]
    assert host.page.inner_text("#lobby-code") == code

    guest.join(code, "Orion")
    host.wait("s.players.length === 2")
    assert "Orion" in host.page.inner_text("#lobby-crew")
    assert not guest.page.is_visible("#start-button")
    assert "Waiting for Nova" in guest.page.inner_text("#lobby-note")

    host.page.click("#start-button")
    hs = host.wait("s.phase === 'playing'")
    gs = guest.wait("s.phase === 'playing'")
    assert hs["positions"] == gs["positions"] and hs["target"] == gs["target"]
    assert not host.page.is_visible("#lobby-panel")

    # Unowned station: the button is disabled and the keyboard explains who owns it.
    foreign = next(i for i in range(4) if gs["owners"][i] != gs["you"])
    guest.page.click(f".ring-chip[data-dial='{foreign}']")
    assert guest.page.is_disabled("#rotate-right")
    guest.page.keyboard.press("ArrowRight")
    guest.page.wait_for_selector("#toast.show")
    assert "belongs to Nova" in guest.page.inner_text("#toast")

    # Chat round-trip.
    guest.page.click("#toggle-comms")
    guest.page.fill("#chat-input", "Turning Ember next <b>ok</b>")
    guest.page.press("#chat-input", "Enter")
    host.wait("s.chat.some(m => m.message.includes('Turning Ember next'))")
    assert "<b>ok</b>" in host.page.text_content("#chat-log")  # shown as text, never as HTML
    assert host.page.locator("#chat-log b").count() == 0

    # Solve round one cooperatively through the UI.
    players = [host, guest]
    s = host.state()
    for n, (dial, direction) in enumerate(solve(s["positions"], s["target"]), start=1):
        owner_page(players, s, dial).move(dial, direction)
        for p in players:
            p.wait(f"s.moves >= {n} || s.phase !== 'playing'")
    for p in players:
        st = p.wait("s.phase === 'intermission'")
        assert st["result"] == "solved"
        p.page.wait_for_selector("#result-panel:not(.hidden)")
        assert "CORE STABILIZED" in p.page.inner_text("#result-title")
    assert host.state()["score"] == guest.state()["score"] > 0


def test_quick_play_with_ai_crewmate_completes_a_round(make_player):
    solo = make_player()
    s = solo.create("Nova", quick=True)
    s = solo.wait("s.phase === 'playing'")
    bots = [p for p in s["players"] if p["bot"]]
    assert len(bots) == 1 and bots[0]["id"] in s["owners"]
    s = play_own_moves_until_solved(solo, 1)
    assert s["history"][0]["result"] == "solved"


def test_refresh_mid_game_rejoins_same_seat(make_player):
    host, guest = make_player(), make_player()
    code = host.create("Nova")["code"]
    me = guest.join(code, "Orion")["you"]
    host.wait("s.players.length === 2")
    host.page.click("#start-button")
    guest.wait("s.phase === 'playing'")
    guest.page.reload()
    again = guest.wait("s.phase === 'playing'")
    assert again["you"] == me
    assert host.wait("s.players.every(p => p.online)")["players"].__len__() == 2


def test_bad_room_code_returns_to_landing_without_retry_loop(make_player):
    p = make_player()
    p.page.goto(p.base)
    p.page.fill("#player-name", "Nova")
    p.page.fill("#room-code-input", "zzzzz")
    p.page.click("#join-room")
    p.page.wait_for_selector("#landing:not(.hidden)")
    assert "not found" in p.page.inner_text("#toast")
    p.page.wait_for_timeout(2500)
    assert p.page.is_visible("#landing") and not p.page.is_visible("#game")


def test_full_room_rejects_newcomer_cleanly(make_player):
    host, late = make_player(), make_player()
    code = host.create("Nova")["code"]
    for n in range(3):
        host.page.click("#add-bot")
        host.wait(f"s.players.length === {n + 2}")
    assert not host.page.is_visible("#add-bot")
    late.join_attempt = late.page.goto(f"{late.base}/?room={code}")
    late.page.fill("#player-name", "Late")
    late.page.click("#join-room")
    late.page.wait_for_selector("#landing:not(.hidden)")
    assert "full" in late.page.inner_text("#toast")


def test_exit_from_lobby_frees_the_seat(make_player):
    host, guest = make_player(), make_player()
    code = host.create("Nova")["code"]
    guest.join(code, "Orion")
    host.wait("s.players.length === 2")
    guest.page.click("#leave-room")
    guest.page.wait_for_selector("#landing:not(.hidden)")
    host.wait("s.players.length === 1")


def test_keyboard_controls_and_hint(make_player):
    p = make_player()
    p.create("Solo")
    p.page.click("#start-button")
    s = p.wait("s.phase === 'playing'")
    p.page.keyboard.press("2")
    assert p.page.evaluate("window.ConfluxDebug.selected") == 1
    p.page.keyboard.press("ArrowRight")
    expected = rotate(s["positions"], 1, 1)
    s = p.wait(f"s.moves === 1 || s.phase !== 'playing'")
    if s["phase"] == "playing":
        assert s["positions"] == expected
        p.page.keyboard.press("h")
        s = p.wait("s.hints === 1")
        assert s["chat"][-1]["kind"] == "hint"


def test_mobile_layout_fits_and_is_playable(make_player):
    p = make_player(viewport={"width": 390, "height": 844}, touch=True)
    p.create("Nova", quick=True)
    s = p.wait("s.phase === 'playing'")
    assert p.page.evaluate("document.documentElement.scrollWidth") <= 390
    for sel in ("#rotate-left", "#rotate-right", "#hint-button", "#leave-room"):
        box = p.page.locator(sel).bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 844, sel
        assert box["height"] >= 28, f"{sel} too small to tap"
    for i in range(4):
        box = p.page.locator(f".ring-chip[data-dial='{i}']").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        hot = p.page.locator(f".ring-hotspot[data-dial='{i}']").bounding_box()
        cx, cy = hot["x"] + hot["width"] / 2, hot["y"] + hot["height"] / 2
        assert 0 < cx < 390 and 0 < cy < 844
    banner = p.page.locator(".bottom-banner").bounding_box()
    hud = p.page.locator("#station-hud").bounding_box()
    assert banner["y"] + banner["height"] <= hud["y"] + 1, "ring banner overlaps the control panel"
    mine = next(i for i in range(4) if s["owners"][i] == s["you"])
    p.page.tap(f".ring-hotspot[data-dial='{mine}']")
    p.page.tap("#rotate-right")
    p.wait("s.moves >= 1 || s.phase !== 'playing'")


def test_native_3d_view_toggles_without_errors(make_player):
    p = make_player()
    p.create("Nova", quick=True)
    p.wait("s.phase === 'playing'")
    p.page.click("#toggle-view")
    assert p.page.evaluate("document.body.classList.contains('native-mode')")
    renderer = p.page.evaluate("""() => {
        const g = document.createElement('canvas').getContext('webgl2');
        const e = g && g.getExtension('WEBGL_debug_renderer_info');
        return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : '';
    }""")
    software = any(k in renderer.lower() for k in ("swiftshader", "llvmpipe", "software"))
    assert p.page.evaluate("window.ConfluxScene.mode") == ("fallback" if software or not renderer else "webgl")
    fps = p.page.evaluate("""() => new Promise(done => { let n = 0; const t0 = performance.now();
        const f = t => (++n < 30 ? requestAnimationFrame(f) : done(30000 / (t - t0))); requestAnimationFrame(f); })""")
    assert fps > 20, f"3D/2D view too slow on this machine: {fps:.1f} fps"
    p.page.wait_for_timeout(1200)
    assert p.page.is_visible("#reset-camera")
    p.page.click("#reset-camera")
    p.page.click("#toggle-view")
    assert not p.page.evaluate("document.body.classList.contains('native-mode')")


def test_offline_practice_file_plays_a_round(make_player, tmp_path):
    out = tmp_path / "practice.html"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo.py"), str(out)], check=True, capture_output=True)
    p = make_player()
    p.page.goto(out.as_uri())
    s = p.wait("s.phase === 'playing'")
    assert p.page.is_visible("#demo-ribbon")
    for dial, direction in solve(s["positions"], s["target"]):
        p.move(dial, direction)
    s = p.wait("s.phase === 'intermission'")
    assert s["result"] == "solved" and s["score"] > 0


def test_3d_view_recovers_from_webgl_context_loss(make_player):
    """Browsers can drop GPU contexts; the 3D view must rebuild instead of going blank."""
    p = make_player()
    p.ctx.add_init_script("localStorage.setItem('conflux-force-webgl','1')")  # exercise WebGL even on software GPUs
    p.create("Nova", quick=True)
    p.wait("s.phase === 'playing'")
    assert p.page.evaluate("window.ConfluxScene.mode") == "webgl"
    p.page.click("#toggle-view")
    p.page.wait_for_timeout(500)
    lost = p.page.evaluate("""() => {
        const gl = document.getElementById('reactor-canvas').getContext('webgl2');
        if (!gl) return 'no-webgl';
        gl.getExtension('WEBGL_lose_context').loseContext();
        return 'lost';
    }""")
    if lost == "no-webgl":
        pytest.skip("WebGL2 unavailable in this browser")
    p.page.wait_for_timeout(800)
    status = p.page.evaluate("""() => {
        const c = document.getElementById('reactor-canvas');
        const gl = c.getContext('webgl2');
        return {live: !!gl && !gl.isContextLost(), count: document.querySelectorAll('#reactor-canvas').length};
    }""")
    assert status == {"live": True, "count": 1}
    s = p.state()
    mine = next(i for i in range(4) if s["owners"][i] == s["you"])
    p.move(mine, 1)
    p.wait("s.moves >= 1 || s.phase !== 'playing'")


LAYOUT_PROBE = """() => {
  const box = s => document.querySelector(s).getBoundingClientRect();
  const overlap = (a, b) => !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
  const offscreen = [...document.querySelectorAll('#station-hud button, .ring-chip, .hud-actions button, #leave-room, .hud-tile')]
    .filter(e => getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden')
    .filter(e => { const r = e.getBoundingClientRect(); return r.right > innerWidth + 1 || r.bottom > innerHeight + 1 || r.left < -1 || r.top < -1; })
    .map(e => e.id || e.className);
  return {
    scrollWidth: document.documentElement.scrollWidth,
    bannerOverHud: overlap(box('#station-hud'), box('.bottom-banner')),
    topOverHud: overlap(box('.hud-top'), box('#station-hud')),
    offscreen,
  };
}"""


@pytest.mark.parametrize("width,height", [(350, 700), (375, 667), (390, 844), (430, 932), (768, 1024),
                                          (1024, 768), (1280, 720), (1440, 900), (1920, 1080)])
def test_layout_has_no_overlap_or_offscreen_controls(make_player, width, height):
    p = make_player(viewport={"width": width, "height": height}, touch=width < 800)
    p.create("Nova", quick=True)
    p.wait("s.phase === 'playing'")
    p.page.wait_for_timeout(300)
    r = p.page.evaluate(LAYOUT_PROBE)
    assert r == {"scrollWidth": width, "bannerOverHud": False, "topOverHud": False, "offscreen": []}, r
