"""Exact finite prior proposals with public Study identity and recovery."""
from copy import deepcopy
import hashlib
import json

from hponas.encoding import as_knob_space
from hponas.prior_sampling import FiniteGuardedPrior
from hponas.searchers.base import BaseSearcher, PendingSuggestionError
from hponas.types import Config, Result
from hponas.capabilities import SearcherCapabilities, MIXED


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class PriorPendingError(PendingSuggestionError):
    """The proposal cap expired; retry or restore the retained branch state."""


class FinitePriorSearcher(BaseSearcher):
    """Sample an ordered finite support under an explicitly declared base law.

    ``base=None`` means uniform over the listed configurations, including for
    transformed or conditional spaces. Supply exact rational cell masses for a
    different pushforward. A finite support never asserts continuous density
    conformance. Config IDs identify draws; Study owns evaluation/trial IDs.
    """

    support = SearcherCapabilities(MIXED, conditionals=True, partial_fidelity=True, prior='external_law')

    def __init__(self, search_space, cells, weights, alpha, seed=0, *, base=None,
                 max_proposals=1, cell_identity="finite-cells-v1"):
        super().__init__(search_space, seed)
        domain = as_knob_space(search_space)
        if type(cells) is not list or not cells or not domain.knobs:
            raise ValueError("A nonempty ordered finite cell list and space are required")
        if type(max_proposals) is not int or max_proposals < 1:
            raise ValueError("max_proposals must be a positive integer")
        if type(cell_identity) is not str or not cell_identity:
            raise ValueError("A nonempty base measure identity is required")
        for cell in cells:
            if type(cell) is not dict or set(cell) - {k.name for k in domain.knobs}:
                raise ValueError("Finite cells must contain only declared coordinates")
            if any(isinstance(v, bool) for v in cell.values()):
                raise ValueError("Boolean finite coordinates are not supported")
            domain.validate_config(cell)
            canonical(cell)
        if any(cell == other for i, cell in enumerate(cells) for other in cells[:i]):
            raise ValueError("Duplicate finite configurations do not define distinct cells")
        self.cells = deepcopy(cells)
        self.max_proposals, self.cell_identity = max_proposals, cell_identity
        self._support = {"space": domain.to_dict(), "cells": self.cells,
                         "base_measure": cell_identity}
        support_hash = hashlib.sha256(canonical(self._support).encode()).hexdigest()
        self._sampler = FiniteGuardedPrior(
            [1] * len(cells) if base is None else base, weights, alpha, seed,
            cell_identity=support_hash,
        )
        if len(self._sampler.base) != len(self.cells):
            raise ValueError("Each cell requires one base mass and prior weight")
        self._draws = []

    @property
    def prior_identity(self):
        return self._sampler.law_sha256

    def suggest(self):
        index = self._sampler.advance(self.max_proposals)
        if index is None:
            raise PriorPendingError("Prior draw pending; its branch and RNG state are checkpointable")
        config = Config(deepcopy(self.cells[index]), f"finite-prior-draw-{len(self._draws)}")
        self._draws.append(index)
        return config

    def _validate_config_binding(self, config):
        if type(config.config_id) is not str or not config.config_id.startswith("finite-prior-draw-"):
            raise ValueError("Prior trial must bind a returned configuration ID")
        suffix = config.config_id.removeprefix("finite-prior-draw-")
        if not suffix.isdecimal() or str(int(suffix)) != suffix:
            raise ValueError("Malformed finite prior draw ID")
        index = int(suffix)
        if index >= len(self._draws) or config.values != self.cells[self._draws[index]]:
            raise ValueError("Prior trial configuration differs from its recorded draw")

    def observe(self, result):
        if not isinstance(result, Result) or result.trial_id not in self.trials:
            raise ValueError("Prior result requires a bound public trial ID")
        self._validate_config_binding(self.trials[result.trial_id])
        if any(old.trial_id == result.trial_id for old in self.history):
            raise ValueError("Prior result cannot be revised")
        super().observe(result)

    def validate_study_snapshot(self, state):
        configs = {tid: row["config"] for tid, row in state["trials"].items()}
        if configs != {tid: cfg.to_dict() for tid, cfg in self.trials.items()}:
            raise ValueError("Prior configuration ledger differs from Study")
        history = {row.trial_id: row.to_dict() for row in self.history}
        # Failed results may carry NaN; serialized comparisons preserve it.
        if json.dumps(history, sort_keys=True) != json.dumps(state["results"], sort_keys=True):
            raise ValueError("Prior observation ledger differs from Study")

    def get_state(self):
        return deepcopy({**super().get_state(), "kind": "finite_prior_searcher_v2",
                         "support": self._support, "max_proposals": self.max_proposals,
                         "prior": self._sampler.state_dict(), "draws": self._draws})

    def set_state(self, state):
        if (type(state) is not dict or set(state) != set(self.get_state())
                or state.get("kind") != "finite_prior_searcher_v2"
                or canonical(state.get("support")) != canonical(self._support)
                or type(state.get("max_proposals")) is not int
                or state["max_proposals"] != self.max_proposals):
            raise ValueError("Finite prior searcher identity differs")
        restored = type(self)(
            self.search_space, self.cells, self._sampler.weights, self._sampler.alpha,
            seed=state["seed"], base=self._sampler.base,
            max_proposals=self.max_proposals, cell_identity=self.cell_identity,
        )
        restored._sampler.load_state_dict(deepcopy(state["prior"]))
        draws = state["draws"]
        if (type(draws) is not list or len(draws) != restored._sampler.completed_draws
                or any(type(i) is not int or not 0 <= i < len(self.cells) for i in draws)):
            raise ValueError("Prior draw ledger contradicts the sampler counters")
        restored._draws = list(draws)
        if type(state["trials"]) is not dict or type(state["history"]) is not list:
            raise ValueError("Invalid prior trial/history ledger")
        try:
            BaseSearcher.set_state(restored, deepcopy(state))
            for tid, config in restored.trials.items():
                if type(tid) is not str or not tid:
                    raise ValueError("Invalid public trial ID")
                restored._validate_config_binding(config)
            ids = [row.trial_id for row in restored.history]
            if len(ids) != len(set(ids)) or not set(ids) <= set(restored.trials):
                raise ValueError("Prior history must bind unique public trial IDs")
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed prior trial/history ledger") from exc
        self.__dict__.update(restored.__dict__)

    @property
    def capabilities(self):
        return {**super().capabilities, "prior": True, "finite_support": True,
                "pending_suggestions": True}
