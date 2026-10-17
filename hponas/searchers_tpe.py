"""
Maintained Optuna TPE implementation. The public Study and Tier 0 campaigns
use it through hponas.searchers.adapter.LegacySearcherAdapter, which translates
the propose/observe API into the current searcher contract.

TPE (Tree-structured Parzen Estimator) searcher via Optuna wrapper.

Survey reference: Ch 4 roadmap-04, ch04-02.
Survey verdict: include, T0, wrap Optuna.
Validation: V01 (implementation parity vs Optuna reference), V04 (beats random floor).

Tier 0: faithful wrapper that exposes Optuna's TPE through our Searcher interface.
Implementation strategy: minimize translation layer to preserve parity for V01.
"""

from __future__ import annotations

import copy
from typing import Any

try:
    import optuna

    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False

from .space import SearchSpace


class TPESearcher:
    """
    TPE searcher wrapping Optuna (Ch 4 roadmap-04, ch04-02).

    Survey verdict: include, T0, ~4 engineer-days.
    Contract: wrap Optuna TPE sampler with minimal translation.
    Validation: V01 parity check, V04 performance check.

    Design: One Optuna study per HPO study, synchronized at observe().
    State recovery: serialize Optuna study via its own serialization.
    """

    def __init__(self, space: SearchSpace, seed: int = 0):
        if not OPTUNA_AVAILABLE:
            raise ImportError("TPESearcher requires optuna: pip install optuna")

        self.space = space
        self.seed = seed
        self._n_proposed = 0
        self._n_observed = 0

        # Create Optuna study with TPE sampler
        sampler = optuna.samplers.TPESampler(seed=seed)
        self._study = optuna.create_study(
            direction="minimize",  # Our interface uses maximize, we'll flip
            sampler=sampler,
        )

        # Build Optuna search space from our SearchSpace
        self._build_optuna_space()

        # Track pending trials (proposed but not yet observed)
        self._pending: dict[int, dict[str, Any]] = {}
        self._next_trial_id = 0
        self._events = []

    def _build_optuna_space(self) -> None:
        """
        Register search space with Optuna.

        Optuna discovers the space from suggest calls, so we don't pre-register.
        Instead, we store the mapping for consistent translation.
        """
        self._knob_map = {}
        for knob in self.space.knobs:
            self._knob_map[knob.name] = knob

    def propose(self, n: int) -> list[dict[str, Any]]:
        """
        Propose n configurations via Optuna TPE.

        Optuna's API is single-ask: create trial, get suggestions.
        We create n trials and return them as a batch.
        """
        configs = []

        for _ in range(n):
            trial = self._study.ask()
            config: dict[str, Any] = {}

            for knob_name, knob in self._knob_map.items():
                if (
                    knob.condition
                    and config.get(knob.condition[0]) != knob.condition[1]
                ):
                    continue
                if knob.kind == "continuous":
                    low, high = knob.bounds
                    if knob.transform == "log":
                        val = trial.suggest_float(knob_name, low, high, log=True)
                    else:
                        val = trial.suggest_float(knob_name, low, high)
                    config[knob_name] = float(val)

                elif knob.kind == "ordinal":
                    low, high = knob.bounds
                    val = trial.suggest_int(knob_name, low, high)
                    config[knob_name] = int(val)

                elif knob.kind == "categorical":
                    val = trial.suggest_categorical(knob_name, knob.bounds)
                    config[knob_name] = val

                else:
                    raise ValueError(f"Unknown knob kind: {knob.kind}")

            # Store trial mapping for later observe()
            self._pending[trial.number] = {
                "trial": trial,
                "config": config,
            }

            configs.append(config)

        self._n_proposed += n
        self._events.append({"action": "propose", "configs": configs})
        return copy.deepcopy(configs)

    def observe(self, trial_result: dict[str, Any]) -> None:
        """
        Ingest one trial result and tell Optuna.

        Expected trial_result format:
        {
            "config": dict[str, Any],
            "value": float,  # objective value
            "fidelity": float | None,
            "cost": float | None,
        }

        Survey: TPE learns from all observations to update its density models.
        """
        config = trial_result["config"]
        value = trial_result["value"]

        # Find matching pending trial by config
        matching_trial_num = None
        for trial_num, pending in self._pending.items():
            if pending["config"] == config:
                matching_trial_num = trial_num
                break

        if matching_trial_num is None:
            raise ValueError(
                f"TPESearcher.observe() called with config not in pending set: {config}"
            )

        pending = self._pending.pop(matching_trial_num)
        optuna_trial = pending["trial"]

        # Tell Optuna the result (flip sign: we maximize, Optuna minimizes)
        self._study.tell(optuna_trial, -value)

        self._n_observed += 1
        self._events.append({"action": "observe", "result": copy.deepcopy(trial_result)})

    def state_dict(self) -> dict[str, Any]:
        """Replayable ask/tell ledger, including pending asks and sampler RNG use."""
        import copy

        return {
            "kind": "tpe",
            "schema_version": 2,
            "seed": self.seed,
            "events": copy.deepcopy(self._events),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        import copy

        if state.get("kind") != "tpe" or state.get("schema_version") != 2:
            raise ValueError(
                "TPE checkpoint requires complete version 2 ask/tell ledger"
            )
        restored = type(self)(self.space, seed=state["seed"])
        for event in copy.deepcopy(state["events"]):
            if event["action"] == "propose":
                if restored.propose(len(event["configs"])) != event["configs"]:
                    raise ValueError(
                        "TPE sampler changed; checkpoint cannot be replayed exactly"
                    )
            elif event["action"] == "observe":
                restored.observe(event["result"])
            else:
                raise ValueError("Unknown TPE checkpoint event")
        self.__dict__.update(restored.__dict__)

    @property
    def support(self):
        from hponas.capabilities import SearcherCapabilities, MIXED
        return SearcherCapabilities(MIXED, conditionals=True, max_dimensions=100)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare TPE capabilities."""
        return self.support.report()
