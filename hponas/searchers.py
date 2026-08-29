"""
Searchers: propose configurations and learn from results.

Survey reference: Ch 15 sec:searcher-interface, Ch 3 (model-free methods).

R1 spike: Sobol searcher only (wraps scipy Sobol + log-scale).
Tier 0: adds GP+qLogEI, TPE wrapper, CMA-ES.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
from scipy.stats import qmc

from .space import SearchSpace


class Searcher(Protocol):
    """
    Searcher interface contract (Ch 15).

    propose(n): return n configurations to evaluate next (batch proposals are normal case).
    observe(trial): ingest one trial result.
    capabilities: static declaration of knob kinds supported, conditionals, priors, max dim.
    """

    def propose(self, n: int) -> list[dict[str, Any]]:
        """Return n configurations to evaluate next."""
        ...

    def observe(self, trial: dict[str, Any]) -> None:
        """Ingest one trial result (config, fidelity, value, cost)."""
        ...

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare what this searcher supports."""
        ...


class SobolSearcher:
    """
    Sobol + log-scale quasi-random sampler (Ch 3 roadmap-01, ch03-01).

    Survey verdict: include, T0, days of work.
    Contract: schema.transform + sobol/log searcher.
    Validation: V04 (beats random floor), V05 (log-warping matters).

    Spike limitation: handles continuous axes only, ignores ordinal/categorical.
    Tier 0: add ordinal (as integer Sobol column) and categorical (Latin hypercube).
    """

    def __init__(self, space: SearchSpace, seed: int = 0):
        self.space = space
        self.seed = seed
        self._rng = np.random.default_rng(seed)

        # Filter to continuous knobs only for spike
        self.cont_knobs = [k for k in space.knobs if k.kind == "continuous" and not k.condition]
        if not self.cont_knobs:
            raise ValueError("SobolSearcher: no continuous knobs in space (spike limitation)")

        self._dim = len(self.cont_knobs)
        self._sobol = qmc.Sobol(d=self._dim, scramble=True, seed=seed)
        self._n_proposed = 0

    def propose(self, n: int) -> list[dict[str, Any]]:
        """
        Propose n configurations via Sobol sequence.
        Survey: batch proposals are the normal case (idle workers in Ch 4).
        """
        # Generate n Sobol points in [0, 1]^d
        points = self._sobol.random(n)

        configs = []
        for point in points:
            config: dict[str, Any] = {}
            for i, knob in enumerate(self.cont_knobs):
                low, high = knob.bounds
                u = point[i]
                if knob.transform == "log":
                    # log-uniform: sample u in [0,1], map to exp(log(low) + u*(log(high)-log(low)))
                    val = np.exp(np.log(low) + u * (np.log(high) - np.log(low)))
                else:
                    val = low + u * (high - low)
                config[knob.name] = float(val)
            configs.append(config)

        self._n_proposed += n
        return configs

    def observe(self, trial: dict[str, Any]) -> None:
        """
        Sobol ignores observations (model-free).
        Survey: a learner would update its surrogate here; Sobol does not.
        """
        pass

    @property
    def capabilities(self) -> dict[str, Any]:
        """
        Declare what this searcher supports (Ch 15 contract).
        Spike: continuous only. Tier 0: add ordinal, categorical, conditionals.
        """
        return {
            "knob_kinds": ["continuous"],
            "conditionals": False,
            "multi_objective": False,
            "prior": False,
            "max_dim": 20,  # reasonable Sobol limit
        }
