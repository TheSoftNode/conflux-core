"""The browser rules (static/logic.js) must agree exactly with game_logic.py."""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from game_logic import STAGE_PAR, STAGE_SECONDS, HINT_PENALTY, rotate, round_points, solve

NODE = shutil.which("node")
LOGIC = Path(__file__).resolve().parents[1] / "static" / "logic.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed")


def run_js(cases):
    script = f"""
const L = require({json.dumps(str(LOGIC))});
const cases = {json.dumps(cases)};
const out = cases.map(c => ({{
  rotate: L.rotate(c.p, c.d, c.dir),
  solve: L.solve(c.p, c.t),
  points: L.roundPoints(true, c.secs, c.moves, c.par, c.hints),
}}));
const puzzles = [1,2,3].map(s => Array.from({{length: 200}}, () => L.newPuzzle(s)));
console.log(JSON.stringify({{out, puzzles, consts: [L.STAGE_PAR, L.STAGE_SECONDS, L.HINT_PENALTY]}}));
"""
    result = subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_js_rules_match_python():
    rng = random.Random(42)
    cases = []
    for _ in range(500):
        t = [rng.randrange(6) for _ in range(4)]
        p = [rng.randrange(6) for _ in range(3)]
        p.append((sum(t) - sum(p)) % 6)
        cases.append({"p": p, "t": t, "d": rng.randrange(4), "dir": rng.choice((-1, 1)),
                      "secs": rng.uniform(0, 90), "moves": rng.randrange(20), "par": rng.randrange(1, 7),
                      "hints": rng.randrange(4)})
    data = run_js(cases)
    for case, js in zip(cases, data["out"]):
        assert js["rotate"] == rotate(case["p"], case["d"], case["dir"])
        assert [tuple(m) for m in js["solve"]] == solve(case["p"], case["t"])
        assert js["points"] == round_points(True, case["secs"], case["moves"], case["par"], case["hints"])
    assert data["consts"] == [[list(r) for r in STAGE_PAR], list(STAGE_SECONDS), HINT_PENALTY]
    for stage, puzzles in enumerate(data["puzzles"], start=1):
        low, high = STAGE_PAR[stage - 1]
        for pz in puzzles:
            assert len(solve(pz["positions"], pz["target"])) == pz["par"]
            assert low <= pz["par"] <= high and pz["positions"] != pz["target"]
