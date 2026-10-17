from hponas.searchers.random_searcher import RandomSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Result


def test_default_best_tracks_valid_replacement_and_recovery():
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    searcher = RandomSearcher(space, seed=7)
    assert searcher.get_best() is None
    for trial_id, value in [("low", -2.), ("high", 4.), ("middle", 1.)]:
        searcher.observe(Result(trial_id, value, 1., 1.))
    searcher.observe(Result("failed", 100., 1., 1., status="failed"))
    assert searcher.get_best().trial_id == "high"
    assert searcher.get_best(maximize=False).trial_id == "low"
    searcher.observe(Result("high", -3., 2., 1.))
    assert searcher.get_best().trial_id == "middle"
    restored = RandomSearcher(space, seed=99)
    restored.set_state(searcher.get_state())
    assert restored.get_best().trial_id == "middle"
    assert restored.get_best(maximize=False).trial_id == "high"

