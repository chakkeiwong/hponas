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
import math
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

    def __init__(self, space: SearchSpace, seed: int = 0, *, model_fidelity: float = 1.):
        if not OPTUNA_AVAILABLE:
            raise ImportError("TPESearcher requires optuna: pip install optuna")

        self.space = space
        self.seed = seed
        if type(model_fidelity) not in (int, float) or not math.isfinite(model_fidelity) or model_fidelity <= 0:
            raise ValueError('Positive finite TPE model_fidelity required')
        self.model_fidelity = float(model_fidelity)
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
        self._roots = {}
        self._registered = {}

    def validate_study_controls(self, max_concurrent, scheduler):
        endpoint = scheduler.config.r_max if scheduler else 1.
        if endpoint != self.model_fidelity:
            raise ValueError('TPE model_fidelity must match the full study endpoint')

    def register_trial(self, trial):
        """Bind asks to immutable root identity before any out-of-order result."""
        root = trial.root_trial_id or trial.trial_id
        if trial.trial_id in self._registered:
            raise ValueError('TPE evaluation identity already registered')
        if root not in self._roots:
            if trial.trial_id != root:
                raise ValueError('TPE promotion lacks a root ask')
            bound = set(self._roots.values())
            available = [n for n in self._pending if n not in bound]
            if not available:
                raise ValueError('TPE root lacks an unbound ask')
            number = available[0]
        else:
            number = self._roots[root]
        if number not in self._pending or self._pending[number]['config'] != trial.config.values:
            raise ValueError('TPE root/ask configuration differs')
        if not 0 < trial.fidelity <= self.model_fidelity:
            raise ValueError('TPE observation exceeds model fidelity')
        self._roots[root] = number
        self._registered[trial.trial_id] = {'root': root, 'number': number, 'fidelity': trial.fidelity,
                                           'config': copy.deepcopy(trial.config.values)}
        self._events.append({'action': 'register', 'trial': copy.deepcopy(trial.to_dict())})

    def observe_result(self, result, *, config, maximize):
        if not self._registered:
            # The standalone adapter contract predates root registration.
            # It remains usable for unambiguous full-endpoint observations.
            if result.fidelity != self.model_fidelity:
                raise ValueError('Partial TPE observations require registered root identity')
            self.observe({'config': config, 'fidelity': result.fidelity,
                          'value': (result.objective_value if maximize else -result.objective_value)
                                   if result.status == 'completed' and result.is_valid() else None})
            return
        row = self._registered.get(result.trial_id)
        if row is None or row['config'] != config or row['fidelity'] != result.fidelity:
            raise ValueError('TPE result lacks matching registered identity')
        number = row['number']
        if number not in self._pending:
            raise ValueError('TPE root ask is already terminal')
        # Keep low rungs in the adapter history, but never train Optuna's
        # density on incomparable partial values (including PRUNED trials).
        if result.is_valid() and result.fidelity < self.model_fidelity:
            return
        value = (result.objective_value if maximize else -result.objective_value)
        self._tell(number, value if result.status == 'completed' and result.is_valid() else None)

    def _tell(self, number, value):
        pending = self._pending[number]
        if value is None:
            self._study.tell(pending['trial'], state=optuna.trial.TrialState.FAIL)
        else:
            if not math.isfinite(value):
                raise ValueError('TPE requires a finite complete value')
            self._study.tell(pending['trial'], -value)
        del self._pending[number]
        self._n_observed += 1
        self._events.append({'action': 'tell', 'number': number, 'value': value})

    def finalize_pending(self):
        for number in list(self._pending):
            self._tell(number, None)

    def validate_study_snapshot(self, state):
        if set(self._registered) != set(state['trials']):
            raise ValueError('TPE registered evaluations differ from Study')
        for tid, trial in state['trials'].items():
            row = self._registered[tid]
            if (row['root'] != state['roots'][tid] or row['config'] != trial['config']['values']
                    or row['fidelity'] != trial['fidelity']):
                raise ValueError('TPE evaluation lineage differs from Study')
        for root, number in self._roots.items():
            values = [r for tid, r in state['results'].items() if state['roots'][tid] == root
                      and r['status'] == 'completed' and r['fidelity'] == self.model_fidelity
                      and math.isfinite(r['objective_value'])]
            vendor = self._study.trials[number]
            if values:
                expected = -values[0]['objective_value'] if state['maximize'] else values[0]['objective_value']
                if len(values) != 1 or vendor.state != optuna.trial.TrialState.COMPLETE or vendor.value != expected:
                    raise ValueError('TPE fitted value differs from full-fidelity Study result')
            elif vendor.state == optuna.trial.TrialState.COMPLETE:
                raise ValueError('TPE trained on a partial or final-role observation')

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

        matching = [n for n, pending in self._pending.items() if pending['config'] == config]
        if 'trial_number' in trial_result:
            matching = [n for n in matching if n == trial_result['trial_number']]
        if not matching:
            raise ValueError(f'TPESearcher.observe() called with config not in pending set: {config}')
        if len(matching) != 1:
            raise ValueError('TPE observation requires one pending ask; supply trial_number for duplicate configurations')
        fidelity = trial_result.get('fidelity', self.model_fidelity)
        if fidelity is not None and fidelity != self.model_fidelity:
            raise ValueError('Direct TPE observe requires model fidelity; use Study for scheduler composition')
        self._tell(matching[0], value)
        self._events[-1] = {'action': 'observe', 'result': copy.deepcopy(trial_result)}

    def state_dict(self) -> dict[str, Any]:
        """Replayable ask/tell ledger, including pending asks and sampler RNG use."""
        import copy

        return {
            "kind": "tpe",
            "schema_version": 3,
            "seed": self.seed,
            "model_fidelity": self.model_fidelity,
            "events": copy.deepcopy(self._events),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        import copy

        if state.get("kind") != "tpe" or state.get("schema_version") != 3:
            raise ValueError(
                "TPE checkpoint requires complete version 3 identity-bound ask/tell ledger"
            )
        if state['model_fidelity'] != self.model_fidelity:
            raise ValueError('TPE checkpoint model fidelity differs')
        restored = type(self)(self.space, seed=state["seed"], model_fidelity=self.model_fidelity)
        for event in copy.deepcopy(state["events"]):
            if event["action"] == "propose":
                if restored.propose(len(event["configs"])) != event["configs"]:
                    raise ValueError(
                        "TPE sampler changed; checkpoint cannot be replayed exactly"
                    )
            elif event["action"] == "register":
                from hponas.types import Trial, Config
                row = event['trial']
                restored.register_trial(Trial(**{**row, 'config': Config(**row['config'])}))
            elif event["action"] == "tell":
                restored._tell(event['number'], event['value'])
            elif event['action'] == 'observe':
                restored.observe(event['result'])
            else:
                raise ValueError("Unknown TPE checkpoint event")
        self.__dict__.update(restored.__dict__)

    @property
    def support(self):
        from hponas.capabilities import SearcherCapabilities, MIXED
        return SearcherCapabilities(MIXED, conditionals=True, partial_fidelity=True, max_dimensions=100)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare TPE capabilities."""
        return self.support.report()
