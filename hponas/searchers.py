"""
Searchers: propose configurations and learn from results.

Survey reference: Ch 15 sec:searcher-interface, Ch 3 (model-free methods).

R1 spike: Sobol searcher only (wraps scipy Sobol + log-scale).
Tier 0: adds GP+qLogEI, TPE wrapper, Random baseline.
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
    state_dict() / load_state_dict(): crash recovery (R1 spike requirement).
    """

    def propose(self, n: int) -> list[dict[str, Any]]:
        """Return n configurations to evaluate next."""
        ...

    def observe(self, trial: dict[str, Any]) -> None:
        """Ingest one trial result (config, fidelity, value, cost)."""
        ...

    def state_dict(self) -> dict[str, Any]:
        """Return serializable state for crash recovery."""
        ...

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state from serialized checkpoint."""
        ...

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare what this searcher supports."""
        ...


class RandomSearcher:
    """
    Uniform random sampling baseline (Ch 3 roadmap-02, ch03-02).

    Survey verdict: include, T0, baseline comparator for V04.
    Contract: handles all knob kinds, respects bounds and transforms.
    Validation: V04 comparator (methods must beat this).

    Tier 0: complete mixed-space implementation.
    """

    def __init__(self, space: SearchSpace, seed: int = 0):
        self.space = space
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self._n_proposed = 0

    def propose(self, n: int) -> list[dict[str, Any]]:
        """Propose n uniformly random configurations."""
        configs = []
        for _ in range(n):
            config: dict[str, Any] = {}
            for knob in self.space.knobs:
                if knob.condition:
                    # Tier 0: conditionals not enforced, sample unconditionally
                    pass

                if knob.kind == "continuous":
                    low, high = knob.bounds
                    if knob.transform == "log":
                        # Log-uniform sampling
                        log_low, log_high = np.log(low), np.log(high)
                        val = np.exp(self._rng.uniform(log_low, log_high))
                    else:
                        val = self._rng.uniform(low, high)
                    config[knob.name] = float(val)

                elif knob.kind == "ordinal":
                    # Sample integer uniformly from bounds
                    low, high = knob.bounds
                    config[knob.name] = int(self._rng.integers(low, high + 1))

                elif knob.kind == "categorical":
                    # Sample from choices uniformly (stored in bounds for categorical)
                    config[knob.name] = self._rng.choice(knob.bounds)

                else:
                    raise ValueError(f"Unknown knob kind: {knob.kind}")

            configs.append(config)

        self._n_proposed += n
        return configs

    def observe(self, trial: dict[str, Any]) -> None:
        """Random search ignores observations (model-free)."""
        pass

    def state_dict(self) -> dict[str, Any]:
        """Serialize state for crash recovery."""
        return {
            "kind": "random",
            "seed": self.seed,
            "n_proposed": self._n_proposed,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore RNG state after crash."""
        if state.get("kind") != "random":
            raise ValueError(f"RandomSearcher cannot load state of kind {state.get('kind')!r}")

        self.seed = state["seed"]
        self._n_proposed = int(state["n_proposed"])

        # Restore RNG by advancing to the same position
        self._rng = np.random.default_rng(self.seed)
        if self._n_proposed > 0:
            # Fast-forward RNG by drawing the same samples
            for _ in range(self._n_proposed):
                for knob in self.space.knobs:
                    if knob.kind == "continuous":
                        self._rng.uniform()
                    elif knob.kind == "ordinal":
                        low, high = knob.bounds
                        self._rng.integers(low, high + 1)
                    elif knob.kind == "categorical":
                        self._rng.choice(knob.bounds)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare support for all knob kinds."""
        return {
            "knob_kinds": ["continuous", "ordinal", "categorical"],
            "conditionals": False,
            "multi_objective": False,
            "prior": False,
            "max_dim": None,  # no dimension limit
        }


class SobolSearcher:
    """
    Sobol + log-scale quasi-random sampler (Ch 3 roadmap-01, ch03-01).

    Survey verdict: include, T0, days of work.
    Contract: schema.transform + sobol/log searcher.
    Validation: V04 (beats random floor), V05 (log-warping matters).

    Tier 0: handles continuous + ordinal (as integer Sobol column),
    categorical via Latin hypercube (uniform sampling).
    """

    def __init__(self, space: SearchSpace, seed: int = 0):
        self.space = space
        self.seed = seed
        self._rng = np.random.default_rng(seed)

        # Separate knobs by kind (Tier 0: handle all kinds)
        self.cont_knobs = [k for k in space.knobs if k.kind == "continuous" and not k.condition]
        self.ord_knobs = [k for k in space.knobs if k.kind == "ordinal" and not k.condition]
        self.cat_knobs = [k for k in space.knobs if k.kind == "categorical" and not k.condition]

        # Sobol covers continuous + ordinal
        self._dim = len(self.cont_knobs) + len(self.ord_knobs)
        if self._dim == 0 and not self.cat_knobs:
            raise ValueError("SobolSearcher: no knobs in space")

        if self._dim > 0:
            self._sobol = qmc.Sobol(d=self._dim, scramble=True, seed=seed)
        else:
            self._sobol = None

        self._n_proposed = 0

    def propose(self, n: int) -> list[dict[str, Any]]:
        """
        Propose n configurations via Sobol sequence + Latin hypercube.
        Survey: batch proposals are the normal case (idle workers in Ch 4).

        Tier 0: continuous and ordinal via Sobol, categorical via uniform sampling.
        """
        configs = []

        if self._sobol is not None:
            # Generate n Sobol points in [0, 1]^d
            points = self._sobol.random(n)
        else:
            points = np.zeros((n, 0))

        for point in points:
            config: dict[str, Any] = {}
            col = 0

            # Continuous knobs from Sobol sequence
            for knob in self.cont_knobs:
                low, high = knob.bounds
                u = point[col]
                if knob.transform == "log":
                    # log-uniform: sample u in [0,1], map to exp(log(low) + u*(log(high)-log(low)))
                    val = np.exp(np.log(low) + u * (np.log(high) - np.log(low)))
                else:
                    val = low + u * (high - low)
                config[knob.name] = float(val)
                col += 1

            # Ordinal knobs from Sobol sequence (integer quantization)
            for knob in self.ord_knobs:
                low, high = knob.bounds
                u = point[col]
                # Map [0, 1] to integer in [low, high]
                val = int(np.floor(low + u * (high - low + 1)))
                val = min(val, high)  # Clamp in case u=1.0
                config[knob.name] = val
                col += 1

            # Categorical knobs: uniform random (not QMC-covered)
            for knob in self.cat_knobs:
                config[knob.name] = self._rng.choice(knob.bounds)

            configs.append(config)

        self._n_proposed += n
        return configs

    def observe(self, trial: dict[str, Any]) -> None:
        """
        Sobol ignores observation *values* (model-free).
        Survey: a learner would update its surrogate here; Sobol does not.

        Note: this does NOT advance the QMC sequence. Position in the sequence is
        tracked by propose() and persisted via state_dict(); replaying observations
        into a fresh searcher does not restore its position. See load_state_dict().
        """
        pass

    def state_dict(self) -> dict[str, Any]:
        """
        Serializable state for crash recovery (Ch 15 contract).

        The QMC sequence position is the load-bearing piece: scipy's Sobol engine
        is stateful, so a searcher rebuilt from the seed alone restarts the sequence
        and re-proposes points that were already evaluated.
        """
        return {
            "kind": "sobol",
            "seed": self.seed,
            "n_proposed": self._n_proposed,
            "cont_knobs": [k.name for k in self.cont_knobs],
            "ord_knobs": [k.name for k in self.ord_knobs],
            "cat_knobs": [k.name for k in self.cat_knobs],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """
        Restore sequence position after a crash.

        Rebuilds the Sobol engine and fast-forwards it past the points already
        proposed, so the resumed study continues the sequence instead of repeating it.
        """
        if state.get("kind") != "sobol":
            raise ValueError(f"SobolSearcher cannot load state of kind {state.get('kind')!r}")

        # Verify knob structure matches
        expected_cont = [k.name for k in self.cont_knobs]
        expected_ord = [k.name for k in self.ord_knobs]
        expected_cat = [k.name for k in self.cat_knobs]

        if (state.get("cont_knobs") != expected_cont or
            state.get("ord_knobs") != expected_ord or
            state.get("cat_knobs") != expected_cat):
            raise ValueError(
                f"Searcher state does not match space: "
                f"state has cont={state.get('cont_knobs')}, ord={state.get('ord_knobs')}, cat={state.get('cat_knobs')}, "
                f"space has cont={expected_cont}, ord={expected_ord}, cat={expected_cat}"
            )

        self.seed = state["seed"]
        self._rng = np.random.default_rng(self.seed)

        if self._dim > 0:
            self._sobol = qmc.Sobol(d=self._dim, scramble=True, seed=self.seed)
            n = int(state["n_proposed"])
            if n > 0:
                self._sobol.fast_forward(n)

        self._n_proposed = int(state["n_proposed"])

        # Fast-forward categorical RNG
        if self.cat_knobs and self._n_proposed > 0:
            for _ in range(self._n_proposed):
                for knob in self.cat_knobs:
                    self._rng.choice(knob.bounds)

    @property
    def capabilities(self) -> dict[str, Any]:
        """
        Declare what this searcher supports (Ch 15 contract).
        Tier 0: continuous, ordinal, categorical. Conditionals deferred.
        """
        return {
            "knob_kinds": ["continuous", "ordinal", "categorical"],
            "conditionals": False,
            "multi_objective": False,
            "prior": False,
            "max_dim": 20,  # reasonable Sobol limit for continuous+ordinal
        }
