"""Thin Optuna/CMA-ES wrapper for unconditional continuous spaces."""

from __future__ import annotations

import copy
from importlib.metadata import version

from hponas.encoding import SpaceEncoder
from hponas.searchers.base import BaseSearcher
from hponas.types import Config


class CMAESSearcher(BaseSearcher):
    """CMA-ES in normalized (optionally log/logit-warped) coordinates.

    Optuna owns the optimizer and asynchronous generation bookkeeping. The
    wrapper translates configurations, completes failed trials explicitly and
    records a JSON ask/tell ledger for exact recovery with the same vendors.
    Install ``hponas[cmaes]`` to use this optional searcher.
    """

    from hponas.capabilities import SearcherCapabilities
    support = SearcherCapabilities(('continuous',))

    def __init__(self, search_space, seed=0, maximize=True):
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        if not isinstance(maximize, bool):
            raise ValueError("maximize must be boolean")
        self._encoder = SpaceEncoder(search_space)
        if not self._encoder.space.knobs or any(
            k.kind != "continuous" or k.condition is not None
            for k in self._encoder.space.knobs
        ):
            raise ValueError("CMA-ES requires a nonempty unconditional continuous space")
        try:
            import cmaes  # noqa: F401 -- fail at construction, not during later sampling
            import optuna
        except ImportError as exc:
            raise ImportError("CMAESSearcher requires pip install 'hponas[cmaes]'") from exc
        super().__init__(search_space, seed)
        self.maximize = maximize
        self._optuna = optuna
        # Always minimize in the vendor, flipping observations for maximization.
        # Study may select direction before the first ask.
        self._study = optuna.create_study(
            direction="minimize", sampler=optuna.samplers.CmaEsSampler(seed=seed)
        )
        self._pending = {}
        self._events = []
        self._versions = {name: version(name) for name in ("optuna", "cmaes")}
        self._direction = None

    def _check_direction(self):
        if not isinstance(self.maximize, bool):
            raise ValueError("maximize must be boolean")
        if self._direction is not None and self._direction != self.maximize:
            raise ValueError("Cannot change direction after CMA-ES has started")
        self._direction = self.maximize

    def suggest(self):
        self._check_direction()
        trial = self._study.ask()
        coordinates = [
            trial.suggest_float(k.name, 0.0, 1.0) for k in self._encoder.space.knobs
        ]
        config = Config(self._encoder.decode(coordinates))
        self._pending[trial.number] = (trial, copy.deepcopy(config.values))
        self._events.append(
            {"action": "suggest", "number": trial.number, "config": copy.deepcopy(config.values)}
        )
        return config

    def observe(self, result):
        self._check_direction()
        if any(old.trial_id == result.trial_id for old in self.history):
            raise ValueError("Cannot revise an observed CMA-ES result")
        if result.trial_id not in self.trials:
            raise ValueError("CMA-ES result has no registered trial configuration")
        config = self.trials[result.trial_id].values
        matching = next(
            (number for number, (_, values) in self._pending.items() if values == config),
            None,
        )
        if matching is None:
            raise ValueError("CMA-ES result does not match a pending suggestion")
        status = "COMPLETE" if result.is_valid() else "FAIL"
        value = (-result.objective_value if self.maximize else result.objective_value) if result.is_valid() else None
        self._tell(matching, value, status)
        super().observe(result)

    def _tell(self, number, value, status):
        if status not in {"COMPLETE", "FAIL"}:
            raise ValueError("Unknown CMA-ES result state")
        self._study.tell(number, value, state=getattr(self._optuna.trial.TrialState, status))
        del self._pending[number]
        self._events.append({"action": "observe", "number": number, "value": value, "status": status})

    def get_state(self):
        return copy.deepcopy({
            **super().get_state(),
            "kind": "cmaes",
            "schema_version": 1,
            "maximize": self.maximize,
            "versions": self._versions,
            "space": self._encoder.space.to_dict(),
            "events": self._events,
        })

    def set_state(self, state):
        if state.get("kind") != "cmaes" or state.get("schema_version") != 1:
            raise ValueError("Unsupported CMA-ES checkpoint")
        if state["versions"] != self._versions:
            raise ValueError("CMA-ES checkpoint requires identical vendor versions")
        if state["space"] != self._encoder.space.to_dict():
            raise ValueError("CMA-ES checkpoint search space differs")
        restored = type(self)(self.search_space, state["seed"], state["maximize"])
        for event in state["events"]:
            if event["action"] == "suggest":
                actual = restored.suggest()
                if actual.values != event["config"] or restored._events[-1]["number"] != event["number"]:
                    raise ValueError("CMA-ES checkpoint does not replay exactly")
            elif event["action"] == "observe":
                restored._tell(event["number"], event["value"], event["status"])
            else:
                raise ValueError("Unknown CMA-ES checkpoint event")
        BaseSearcher.set_state(restored, copy.deepcopy(state))
        self.__dict__.update(restored.__dict__)

    @property
    def capabilities(self):
        return self.support.report()
