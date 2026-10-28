import random
from game_logic import Puzzle, rotate, N_DIALS, SYMBOLS

def test_rotate_inverse_and_coupling():
    initial = [0, 1, 2, 3]
    for dial in range(N_DIALS):
        advanced = rotate(initial, dial, 1)
        assert advanced[dial] == (initial[dial] + 1) % len(SYMBOLS)
        assert advanced[(dial+1)%N_DIALS] == (initial[(dial+1)%N_DIALS] - 1) % len(SYMBOLS)
        assert rotate(advanced, dial, -1) == initial

def test_puzzle_always_starts_unsolved():
    for i in range(500):
        game = Puzzle.new(1 + (i%3), random.Random(i))
        assert game.target != game.positions
        assert len(game.positions) == len(game.target) == N_DIALS
        assert all(0 <= n < len(SYMBOLS) for n in game.positions)

def test_all_puzzles_reachable_mod_six():
    # Every move conserves the sum of symbol indices modulo six.
    # Generating starts by legal moves from targets guarantees same invariant.
    for i in range(250):
        game = Puzzle.new(1 + i%3, random.Random(i))
        assert sum(game.positions) % len(SYMBOLS) == sum(game.target) % len(SYMBOLS)

def test_solve_when_targets_match():
    game = Puzzle(stage=1,target=[0,0,0,0],positions=[5,1,0,0])
    assert not game.solved
    assert game.move(0,1)
    assert game.solved
