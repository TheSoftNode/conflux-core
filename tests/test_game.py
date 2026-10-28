"""Puzzle rules: coupling, solvability, optimal solver, generation and scoring."""
from collections import deque
import itertools
import random

import pytest

from game_logic import (HINT_PENALTY, N_DIALS, N_STAGES, STAGE_PAR, SYMBOLS, Puzzle, rotate,
                        round_points, solvable, solve)


def bfs_distances(target):
    """Brute-force shortest distance from every reachable state to target."""
    dist = {tuple(target): 0}
    queue = deque([tuple(target)])
    while queue:
        state = queue.popleft()
        for dial in range(N_DIALS):
            for direction in (-1, 1):
                nxt = tuple(rotate(list(state), dial, direction))
                if nxt not in dist:
                    dist[nxt] = dist[state] + 1
                    queue.append(nxt)
    return dist


def test_rotate_moves_selected_and_next_clockwise_station():
    initial = [0, 1, 2, 3]
    for dial in range(N_DIALS):
        advanced = rotate(initial, dial, 1)
        assert advanced[dial] == (initial[dial] + 1) % len(SYMBOLS)
        assert advanced[(dial + 1) % N_DIALS] == (initial[(dial + 1) % N_DIALS] - 1) % len(SYMBOLS)
        untouched = [i for i in range(N_DIALS) if i not in (dial, (dial + 1) % N_DIALS)]
        assert all(advanced[i] == initial[i] for i in untouched)
        assert rotate(advanced, dial, -1) == initial


def test_rotate_wraps_last_station_onto_first():
    assert rotate([0, 0, 0, 5], 3, 1) == [5, 0, 0, 0]


@pytest.mark.parametrize("dial,direction", [(-1, 1), (4, 1), (0, 0), (0, 2), (1.0, 1), (True, 1), (0, True)])
def test_rotate_rejects_invalid_input(dial, direction):
    with pytest.raises(ValueError):
        rotate([0, 0, 0, 0], dial, direction)


def test_rotate_does_not_mutate_input():
    positions = [1, 2, 3, 4]
    rotate(positions, 0, 1)
    assert positions == [1, 2, 3, 4]


def test_reachable_states_are_exactly_the_invariant_class():
    dist = bfs_distances([0, 0, 0, 0])
    expected = {s for s in itertools.product(range(6), repeat=4) if sum(s) % 6 == 0}
    assert set(dist) == expected


@pytest.mark.parametrize("target", [[0, 0, 0, 0], [1, 4, 2, 5], [5, 5, 0, 3]])
def test_solver_is_optimal_and_correct_for_every_reachable_state(target):
    dist = bfs_distances(target)
    for state, best in dist.items():
        plan = solve(list(state), target)
        assert len(plan) == best, (state, plan)
        current = list(state)
        for dial, direction in plan:
            current = rotate(current, dial, direction)
        assert current == target


def test_solver_rejects_unreachable_puzzle():
    assert not solvable([0, 0, 0, 1], [0, 0, 0, 0])
    with pytest.raises(ValueError):
        solve([0, 0, 0, 1], [0, 0, 0, 0])


def test_solver_plan_moves_commute_so_any_order_works():
    rng = random.Random(7)
    for _ in range(200):
        puzzle = Puzzle.new(rng.randint(1, 3), rng)
        plan = puzzle.plan()
        rng.shuffle(plan)
        current = puzzle.positions
        for dial, direction in plan:
            current = rotate(current, dial, direction)
        assert current == puzzle.target


@pytest.mark.parametrize("stage", range(1, N_STAGES + 1))
def test_generated_puzzles_match_stage_difficulty(stage):
    low, high = STAGE_PAR[stage - 1]
    for seed in range(300):
        puzzle = Puzzle.new(stage, random.Random(seed))
        assert puzzle.positions != puzzle.target
        assert len(puzzle.positions) == len(puzzle.target) == N_DIALS
        assert all(0 <= n < len(SYMBOLS) for n in puzzle.positions + puzzle.target)
        assert solvable(puzzle.positions, puzzle.target)
        assert low <= puzzle.par <= high
        assert puzzle.par == len(solve(puzzle.positions, puzzle.target))


def test_difficulty_escalates_between_rounds():
    assert STAGE_PAR[0][1] < STAGE_PAR[1][0] and STAGE_PAR[1][1] < STAGE_PAR[2][0]


def test_move_counts_and_detects_solution():
    game = Puzzle(stage=1, target=[0, 0, 0, 0], positions=[5, 1, 0, 0], par=1)
    assert not game.solved and game.matches == 2
    assert game.move(0, 1)
    assert game.solved and game.moves == 1 and game.matches == 4


def test_round_points():
    assert round_points(False, 80, 3, 3, 0) == 0
    assert round_points(True, 60.9, 3, 3, 0) == 150 + 60 * 12 + 120
    assert round_points(True, 60, 5, 3, 0) == 150 + 720 + 120 - 30
    assert round_points(True, 60, 3, 3, 2) == 150 + 720 + 120 - 2 * HINT_PENALTY
    assert round_points(True, 0, 50, 3, 9) == 50  # never below the floor when solved
