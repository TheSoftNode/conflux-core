/* CONFLUX CORE — puzzle rules shared by the browser client and offline practice.
   Mirrors game_logic.py exactly; tests/test_js_parity.py checks both agree. */
(function (root) {
'use strict';
const SYMBOLS = ['✦', '◆', '⬢', '✳', '◈', '●'];
const STATIONS = ['AETHER', 'EMBER', 'PULSE', 'PRISM'];
const N = STATIONS.length, S = SYMBOLS.length;
const STAGE_SECONDS = [90, 80, 70];
const STAGE_PAR = [[2, 3], [4, 5], [6, 6]];
const HINT_PENALTY = 75;
const mod = n => ((n % S) + S) % S;
const signed = n => { n = mod(n); return n > S / 2 ? n - S : n; };

function rotate(positions, dial, direction) {
  if (!Number.isInteger(dial) || dial < 0 || dial >= N) throw new Error('Unknown dial');
  if (direction !== 1 && direction !== -1) throw new Error('Direction must be -1 or 1');
  const next = positions.slice();
  next[dial] = mod(next[dial] + direction);
  next[(dial + 1) % N] = mod(next[(dial + 1) % N] - direction);
  return next;
}

function solvable(positions, target) {
  return mod(positions.reduce((a, b) => a + b, 0)) === mod(target.reduce((a, b) => a + b, 0));
}

function solve(positions, target) {
  if (!solvable(positions, target)) throw new Error('Puzzle is unreachable under the coupled rule');
  const diffs = positions.map((p, i) => mod(target[i] - p));
  let best = null;
  for (let last = 0; last < S; last++) {
    let previous = last; const turns = [];
    for (const delta of diffs) { previous = mod(previous + delta); turns.push(signed(previous)); }
    const cost = turns.reduce((a, n) => a + Math.abs(n), 0);
    if (best === null || cost < best.cost) best = { cost, turns };
  }
  const moves = [];
  best.turns.forEach((n, i) => { for (let k = 0; k < Math.abs(n); k++) moves.push([i, n > 0 ? 1 : -1]); });
  return moves;
}

function roundPoints(won, secondsLeft, moves, par, hints) {
  if (!won) return 0;
  const extra = Math.max(0, moves - par);
  return Math.max(50, 150 + Math.floor(secondsLeft) * 12 + Math.max(0, 120 - 15 * extra) - HINT_PENALTY * hints);
}

function newPuzzle(stage, random = Math.random) {
  const [low, high] = STAGE_PAR[Math.min(Math.max(stage, 1), STAGE_PAR.length) - 1];
  const pick = () => Math.floor(random() * S);
  for (let attempt = 0; attempt < 10000; attempt++) {
    const target = [pick(), pick(), pick(), pick()];
    const positions = [pick(), pick(), pick()];
    positions.push(mod(target.reduce((a, b) => a + b, 0) - positions.reduce((a, b) => a + b, 0)));
    const par = solve(positions, target).length;
    if (par >= low && par <= high) return { stage, target, positions, par, moves: 0 };
  }
  throw new Error('Could not generate a puzzle');
}

const api = { SYMBOLS, STATIONS, STAGE_SECONDS, STAGE_PAR, HINT_PENALTY, rotate, solvable, solve, roundPoints, newPuzzle };
if (typeof module === 'object' && module.exports) module.exports = api;
else root.ConfluxLogic = api;
})(typeof window !== 'undefined' ? window : globalThis);
