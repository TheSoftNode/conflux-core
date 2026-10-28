"""Deterministic, testable core of the CONFLUX CORE puzzle.

Each player's action changes both their own dial and the dial to its right.
The starting puzzle is generated from a target by legal moves, so the
solution always remains reachable.
"""
from dataclasses import dataclass, field
import random

SYMBOLS = ("✦", "◆", "⬢", "✳", "◈", "●")
N_DIALS = 4
N_STAGES = 3
STAGE_SECONDS = (90, 80, 70)


def rotate(positions: list[int], dial: int, direction: int) -> list[int]:
    if not (0 <= dial < N_DIALS):
        raise ValueError("Unknown dial")
    if direction not in (-1, 1):
        raise ValueError("Direction must be -1 or 1")
    new = positions[:]
    new[dial] = (new[dial] + direction) % len(SYMBOLS)
    neighbor = (dial + 1) % N_DIALS
    new[neighbor] = (new[neighbor] - direction) % len(SYMBOLS)
    return new


@dataclass
class Puzzle:
    stage: int = 1
    target: list[int] = field(default_factory=list)
    positions: list[int] = field(default_factory=list)
    moves: int = 0

    @classmethod
    def new(cls, stage: int, rng: random.Random | None = None) -> 'Puzzle':
        rng = rng or random.SystemRandom()
        target = [rng.randrange(len(SYMBOLS)) for _ in range(N_DIALS)]
        positions = target[:]
        # Working backward via valid moves guarantees reachability.
        for _ in range(5 + stage * 3):
            positions = rotate(positions, rng.randrange(N_DIALS), rng.choice((-1, 1)))
        if positions == target:
            positions = rotate(positions, 0, 1)
        return cls(stage=stage, target=target, positions=positions)

    def move(self, dial: int, direction: int) -> bool:
        self.positions = rotate(self.positions, dial, direction)
        self.moves += 1
        return self.solved

    @property
    def solved(self) -> bool:
        return self.positions == self.target

    @property
    def matches(self) -> int:
        return sum(x == y for x, y in zip(self.positions, self.target))
