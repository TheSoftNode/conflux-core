"""Deterministic, testable core of the CONFLUX CORE puzzle.

Four stations sit clockwise around the reactor. Turning station ``i`` by ``d``
(+1 or -1) moves it one symbol and counter-rotates the next station clockwise,
``(i + 1) % 4``, by ``-d``. Every move conserves ``sum(positions) % 6``, so a
puzzle is solvable exactly when its positions and target share that sum.

``solve`` returns a provably shortest move list. Moves commute, so a plan can
be split between players and executed in any order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random

SYMBOLS = ("✦", "◆", "⬢", "✳", "◈", "●")
# Clockwise around the arena: top-left, top-right, bottom-right, bottom-left.
STATIONS = ("AETHER", "EMBER", "PULSE", "PRISM")
N_DIALS = len(STATIONS)
N_SYMBOLS = len(SYMBOLS)
N_STAGES = 3
STAGE_SECONDS = (90, 80, 70)
# Optimal-solution length ("par") for each round, so difficulty always escalates.
# No reachable layout needs more than six moves, so round three is the hardest tier.
STAGE_PAR = ((2, 3), (4, 5), (6, 6))
HINT_PENALTY = 75


def rotate(positions: list[int], dial: int, direction: int) -> list[int]:
    if type(dial) is not int or not (0 <= dial < N_DIALS):
        raise ValueError("Unknown dial")
    if direction not in (-1, 1) or type(direction) is not int:
        raise ValueError("Direction must be -1 or 1")
    new = list(positions)
    new[dial] = (new[dial] + direction) % N_SYMBOLS
    neighbor = (dial + 1) % N_DIALS
    new[neighbor] = (new[neighbor] - direction) % N_SYMBOLS
    return new


def solvable(positions: list[int], target: list[int]) -> bool:
    return sum(positions) % N_SYMBOLS == sum(target) % N_SYMBOLS


def _signed(n: int) -> int:
    n %= N_SYMBOLS
    return n - N_SYMBOLS if n > N_SYMBOLS // 2 else n


def solve(positions: list[int], target: list[int]) -> list[tuple[int, int]]:
    """Shortest list of (dial, direction) moves turning positions into target.

    Let x_i be the net turns applied to dial i. Dial j changes by
    x_j - x_(j-1), so x_j = x_(j-1) + diff_j (mod 6). Choosing x_3 fixes the
    rest; each x_i is then taken as its smallest signed representative. The
    minimum over the six choices of x_3 is optimal because any move sequence
    with the same net residues costs at least sum(|x_i|).
    """
    if not solvable(positions, target):
        raise ValueError("Puzzle is unreachable under the coupled rule")
    diffs = [(t - p) % N_SYMBOLS for p, t in zip(positions, target)]
    best: tuple[int, list[int]] | None = None
    for last in range(N_SYMBOLS):
        turns, previous = [], last
        for delta in diffs:
            previous = (previous + delta) % N_SYMBOLS
            turns.append(_signed(previous))
        cost = sum(abs(n) for n in turns)
        if best is None or cost < best[0]:
            best = (cost, turns)
    assert best is not None
    return [(i, 1 if n > 0 else -1) for i, n in enumerate(best[1]) for _ in range(abs(n))]


def round_points(won: bool, seconds_left: float, moves: int, par: int, hints: int) -> int:
    """Points for one round. Expired rounds score zero."""
    if not won:
        return 0
    extra = max(0, moves - par)
    points = 150 + int(seconds_left) * 12 + max(0, 120 - 15 * extra) - HINT_PENALTY * hints
    return max(50, points)


@dataclass
class Puzzle:
    stage: int = 1
    target: list[int] = field(default_factory=list)
    positions: list[int] = field(default_factory=list)
    moves: int = 0
    par: int = 0

    @classmethod
    def new(cls, stage: int, rng: random.Random | None = None) -> 'Puzzle':
        rng = rng or random.SystemRandom()
        low, high = STAGE_PAR[min(max(stage, 1), N_STAGES) - 1]
        for _ in range(10_000):
            target = [rng.randrange(N_SYMBOLS) for _ in range(N_DIALS)]
            positions = [rng.randrange(N_SYMBOLS) for _ in range(N_DIALS - 1)]
            # The last dial is forced so the start shares the target's invariant.
            positions.append((sum(target) - sum(positions)) % N_SYMBOLS)
            par = len(solve(positions, target))
            if low <= par <= high:
                return cls(stage=stage, target=target, positions=positions, par=par)
        raise RuntimeError("Could not generate a puzzle")  # pragma: no cover

    def move(self, dial: int, direction: int) -> bool:
        self.positions = rotate(self.positions, dial, direction)
        self.moves += 1
        return self.solved

    def plan(self) -> list[tuple[int, int]]:
        return solve(self.positions, self.target)

    @property
    def solved(self) -> bool:
        return self.positions == self.target

    @property
    def matches(self) -> int:
        return sum(x == y for x, y in zip(self.positions, self.target))
