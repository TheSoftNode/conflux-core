"""Static integrity: assets, DOM/JS wiring, offline build, deploy config."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from server import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_all_game_assets_are_served_locally():
    with TestClient(app) as client:
        html = client.get("/").text
        assets = re.findall(r'(?:src|href|srcset)="(/static/[^"?]+)', html)
        assert {"/static/app.js", "/static/logic.js", "/static/scene.js", "/static/fallback.js", "/static/style.css"} <= set(assets)
        for path in set(assets) | {"/static/cover.png"}:
            assert client.get(path).status_code == 200, path
        assert "cdn." not in html and "https://" not in html
        assert 'id="reactor-canvas"' in html


def test_every_element_id_used_by_app_js_exists_in_index_html():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    dynamic = set(re.findall(r'id="([^"$]+)"', js))  # created by app.js itself
    used = set(re.findall(r"\$\('([^']+)'\)", js))
    missing = used - ids - dynamic
    assert not missing, f"app.js references missing elements: {sorted(missing)}"
    assert len(ids) == len(re.findall(r'id="[^"]+"', html)), "duplicate ids in index.html"


def test_scripts_load_in_dependency_order():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    order = [html.index(f"/static/{n}") for n in ("logic.js", "fallback.js", "scene.js", "app.js")]
    assert order == sorted(order)


def test_offline_build_is_fully_self_contained(tmp_path):
    import subprocess, sys
    out = tmp_path / "demo.html"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo.py"), str(out)], check=True, capture_output=True)
    html = out.read_text(encoding="utf-8")
    assert "window.CONFLUX_OFFLINE = true" in html
    assert "/static/" not in html and "{{VERSION}}" not in html
    assert "data:image/webp;base64," in html and "ConfluxLogic" in html
    assert html.count("<script") == 1


def test_deploy_configs_use_a_single_worker():
    for name in ("render.yaml", "Dockerfile"):
        text = (ROOT / name).read_text()
        assert "--workers 1" in text and "server:app" in text
    assert "healthCheckPath: /health" in (ROOT / "render.yaml").read_text()


def test_station_names_match_between_server_and_client():
    js = (STATIC / "logic.js").read_text(encoding="utf-8")
    names = re.search(r"const STATIONS = \[([^\]]+)\]", js).group(1)
    assert [n.strip(" '") for n in names.split(",")] == list(server.STATIONS)
