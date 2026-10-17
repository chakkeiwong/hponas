"""Explicit bridge from propose/dictionary searchers to the Study contract."""

from __future__ import annotations
from copy import deepcopy
from hponas.searchers.base import BaseSearcher
from hponas.types import Config


class LegacySearcherAdapter(BaseSearcher):
    def __init__(self, searcher, maximize=True):
        if getattr(searcher, "objectives", None):
            raise TypeError(
                "Scalar Study requires a scalar searcher; use the multi-objective campaign API"
            )
        super().__init__(searcher.space, searcher.seed)
        self.searcher = searcher
        self.maximize = maximize

    def suggest(self):
        return Config(self.searcher.propose(1)[0])

    def validate_study_context(self, study_name):
        if hasattr(self.searcher, "validate_study_context"):
            self.searcher.validate_study_context(study_name, self.maximize)

    def validate_study_controls(self, max_concurrent, scheduler):
        if hasattr(self.searcher, "validate_study_controls"):
            self.searcher.validate_study_controls(max_concurrent, scheduler)

    def validate_study_snapshot(self, state):
        if hasattr(self.searcher, "validate_study_snapshot"):
            self.searcher.validate_study_snapshot(state)

    @property
    def support(self):
        return getattr(self.searcher, 'support', None)

    @property
    def capabilities(self):
        return {**super().capabilities, **getattr(self.searcher, 'capabilities', {})}

    def observe(self, result):
        if any(r.trial_id == result.trial_id for r in self.history):
            raise ValueError("Legacy adapter cannot revise an already observed result")
        if hasattr(self.searcher, 'observe_result'):
            self.searcher.observe_result(result, config=self.trials[result.trial_id].values,
                                         maximize=self.maximize)
            super().observe(result)
            return
        super().observe(result)
        if not result.is_valid():
            return
        # Legacy scalar wrappers expose maximization (including the Optuna wrapper).
        value = result.objective_value if self.maximize else -result.objective_value
        self.searcher.observe(
            {
                "config": self.trials[result.trial_id].values,
                "value": value,
                "fidelity": result.fidelity,
                "cost": result.cost,
            }
        )

    def get_state(self):
        return {
            **super().get_state(),
            "legacy": self.searcher.state_dict(),
            "maximize": self.maximize,
        }

    def set_state(self, state):
        candidate = deepcopy(self)
        BaseSearcher.set_state(candidate, state)
        if type(state['maximize']) is not bool:
            raise ValueError('Legacy adapter direction must be boolean')
        candidate.maximize = state["maximize"]
        candidate.searcher.load_state_dict(state["legacy"])
        self.__dict__.update(candidate.__dict__)
