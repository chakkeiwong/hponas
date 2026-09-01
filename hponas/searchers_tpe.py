"""
TPE (Tree-structured Parzen Estimator) searcher via Optuna wrapper.

Survey reference: Ch 4 roadmap-04, ch04-02.
Survey verdict: include, T0, wrap Optuna.
Validation: V01 (implementation parity vs Optuna reference), V04 (beats random floor).

Tier 0: faithful wrapper that exposes Optuna's TPE through our Searcher interface.
Implementation strategy: minimize translation layer to preserve parity for V01.
"""

from __future__ import annotations

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

    def _build_optuna_space(self) -> None:
        """
        Register search space with Optuna.

        Optuna discovers the space from suggest calls, so we don't pre-register.
        Instead, we store the mapping for consistent translation.
        """
        self._knob_map = {}
        for knob in self.space.knobs:
            if knob.condition:
                # Tier 0: conditionals not implemented
                continue

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
                    val = trial.suggest_categorical(knob_name, knob.choices)
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
        return configs

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

    def state_dict(self) -> dict[str, Any]:
        """
        Serialize state for crash recovery.

        Optuna study can be pickled, but for portability we serialize
        trial history and reconstruct.
        """
        # Extract trial history
        trials_data = []
        for trial in self._study.trials:
            trials_data.append({
                "number": trial.number,
                "params": trial.params,
                "value": trial.value,
                "state": trial.state.name,
            })

        return {
            "kind": "tpe",
            "seed": self.seed,
            "n_proposed": self._n_proposed,
            "n_observed": self._n_observed,
            "trials": trials_data,
            "pending_count": len(self._pending),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """
        Restore state after crash.

        Reconstructs Optuna study by replaying completed trials.
        Pending trials are lost (expected: executor will re-propose them).
        """
        if state.get("kind") != "tpe":
            raise ValueError(f"TPESearcher cannot load state of kind {state.get('kind')!r}")

        self.seed = state["seed"]
        self._n_proposed = state["n_proposed"]
        self._n_observed = state["n_observed"]

        # Rebuild Optuna study
        sampler = optuna.samplers.TPESampler(seed=self.seed)
        self._study = optuna.create_study(
            direction="minimize",
            sampler=sampler,
        )

        # Replay completed trials
        for trial_data in state["trials"]:
            if trial_data["state"] == "COMPLETE":
                # Use enqueue_trial to replay with exact params
                self._study.enqueue_trial(trial_data["params"])
                trial = self._study.ask()
                self._study.tell(trial, trial_data["value"])

        # Pending trials are not restored (crash loses in-flight work)
        self._pending = {}
        self._next_trial_id = len(self._study.trials)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare TPE capabilities."""
        return {
            "knob_kinds": ["continuous", "ordinal", "categorical"],
            "conditionals": False,  # Tier 0: not implemented
            "multi_objective": False,
            "prior": False,
            "max_dim": 100,  # Optuna TPE scales well
        }
