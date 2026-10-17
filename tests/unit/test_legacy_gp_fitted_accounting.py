"""Public fitted proposal accounting uses the real GP and acquisition path."""

from hponas.searchers_gp import GPqLogEISearcher
from hponas.space import Knob, SearchSpace


def test_fitted_proposals_accumulate_after_bootstrap_and_recovery():
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    target = GPqLogEISearcher(space, seed=13, n_fantasies=4, raw_samples=8, n_restarts=1)
    initial = target.propose(2)
    for config in initial:
        target.observe({"config": config, "value": -(config["x"] - .4) ** 2})
    assert target.state_dict()["n_proposed"] == 2
    for expected in (3, 4):
        config, = target.propose(1)
        space.validate_config(config)
        state = target.state_dict()
        assert state["n_proposed"] == expected
        restored = GPqLogEISearcher(space)
        restored.load_state_dict(state)
        assert restored.state_dict() == state
        target = restored
