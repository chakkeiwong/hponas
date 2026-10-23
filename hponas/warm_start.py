"""Opt-in ranked configuration seeding from explicit, completed run-store history.

Ranked initialization transfers configurations only. The separate opt-in
fixed-kernel RGPE searcher lives in hponas.rgpe. Empirical transfer speedup and
the V12 performance/default decision remain unestablished.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Optional, Sequence, TYPE_CHECKING

from .searchers.base import BaseSearcher
from .space import SearchSpace
from .types import Config
from .warm_history import SeedQueue, physical_key, select, space_signature

if TYPE_CHECKING:
    from .store import Store


def _checkpoint_json(value):
    # Core Result checkpoints retain failed/nonfinite observations as such.
    # Selection/history JSON remains strictly finite; this encoding follows the
    # existing searcher checkpoint contract and preserves the raw failures.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True)


def checkpoint_digest(value):
    return hashlib.sha256(_checkpoint_json(value).encode()).hexdigest()


def check_space_compatibility(source_space_json: str, target_space: SearchSpace) -> bool:
    """Compare all coordinate semantics, including transforms and conditions."""
    try:
        return space_signature(SearchSpace.from_json(source_space_json)) == space_signature(target_space)
    except (ValueError, KeyError, TypeError):
        return False


def load_seed_selection(store, target_space, *, context, n=10, study_ids=None,
                        exclude_study_ids=()):
    """Read one immutable history snapshot; never infer absent eligibility."""
    if type(n) is not int or n < 0:
        raise ValueError("Selection limit must be a nonnegative integer")
    if context is None:
        return None
    histories = [s for s in store.read_warm_histories()
                 if (study_ids is None or s["study_id"] in study_ids)
                 and s["study_id"] not in exclude_study_ids]
    return select(histories, context, target_space, n)


def load_seed_configs(store: Store, study_id: str, target_space: SearchSpace,
                      n: int = 10, objective: str = "minimize", *, context=None) -> list[dict]:
    """Load within-study ranked seeds when explicit eligibility is available.

    Old records without a frozen history/context yield an empty cold-start seed
    list. A matching space alone does not establish comparable objectives/tasks.
    """
    return load_seed_configs_from_all_studies(store, target_space, n, objective,
                                             context=context, study_ids=[study_id])


def load_seed_configs_from_all_studies(store: Store, target_space: SearchSpace,
                                       n: int = 10, objective: str = "minimize",
                                       exclude_study_ids: Optional[Sequence[str]] = None,
                                       *, context=None, study_ids=None) -> list[dict[str, Any]]:
    """Deduplicate configurations ordered by exact within-study quantiles."""
    if objective not in {"minimize", "maximize"}:
        raise ValueError("Invalid objective direction")
    if context is not None and context.get("direction") != objective:
        raise ValueError("Target context and objective direction differ")
    selection = load_seed_selection(store, target_space, context=context, n=n,
                                    study_ids=study_ids, exclude_study_ids=exclude_study_ids or ())
    return [] if selection is None else [deepcopy(r["config"]) for r in selection["seeds"]]


def _validate_selection(selection, space):
    SeedQueue(selection)  # Validate immutable content binding.
    if selection.get("schema") != "ranked_history_v1":
        raise ValueError("Unsupported ranked selection schema")
    select([], selection["context"], space, selection["limit"])
    if len(selection["seeds"]) > selection["limit"]:
        raise ValueError("Selection exceeds its registered seed limit")
    keys, previous = set(), None
    from fractions import Fraction
    for row in selection["seeds"]:
        if set(row) != {"study_id", "trial_id", "config", "quantile"}:
            raise ValueError("Malformed ranked seed")
        if any(not isinstance(row[k], str) or not row[k] for k in ["study_id", "trial_id"]):
            raise ValueError("Missing ranked seed identity")
        if row["study_id"] == selection["context"]["study_id"]:
            raise ValueError("Target study cannot seed itself")
        q = row["quantile"]
        if (not isinstance(q, list) or len(q) != 2 or any(type(v) is not int for v in q)
                or not 0 < q[0] < q[1]):
            raise ValueError("Invalid empirical quantile")
        order = (Fraction(*q), row["study_id"], row["trial_id"])
        key = physical_key(space, row["config"])
        if key in keys or (previous is not None and order < previous):
            raise ValueError("Seeds must be uniquely and deterministically ranked")
        keys.add(key)
        previous = order


class WarmStartSearcher:
    """Dictionary/propose compatibility wrapper; use RankedWarmStartSearcher for Study.

    Explicit manual seeds remain supported. Store-based seeding requires a target
    context and immutable completed history. Recovery validates a detached base
    before committing the base and seed queue together.
    """
    def __init__(self, base: Any, seed_configs: Sequence[dict[str, Any]], *, selection=None):
        self._base = base
        self._selection = deepcopy(selection)
        self._seed_configs = []
        seen = set()
        for config in seed_configs:
            key = physical_key(self.space, config)
            if key not in seen:
                self._seed_configs.append(deepcopy(config))
                seen.add(key)
        if selection is not None:
            _validate_selection(selection, self.space)
            if self._seed_configs != [r["config"] for r in selection["seeds"]]:
                raise ValueError("Seed configurations and selection differ")
        self._n_seeds_used = 0
        self.fallback_reason = None if self._seed_configs else "no_eligible_history"

    @property
    def space(self):
        return self._base.space

    @property
    def seed(self):
        return self._base.seed

    @classmethod
    def from_store(cls, base, store, space, study_id=None, n=10, objective="minimize", *, context=None):
        if space_signature(base.space) != space_signature(space):
            raise ValueError("Base searcher and requested space differ")
        if objective not in {"minimize", "maximize"} or (context is not None and context.get("direction") != objective):
            raise ValueError("Target context and objective direction differ")
        selection = load_seed_selection(store, space, context=context, n=n,
                                        study_ids=None if study_id is None else [study_id])
        configs = [] if selection is None else [r["config"] for r in selection["seeds"]]
        result = cls(base, configs, selection=selection)
        if context is None:
            result.fallback_reason = "missing_target_context"
        return result

    @property
    def n_seeds_remaining(self):
        return len(self._seed_configs) - self._n_seeds_used

    @property
    def n_seeds_used(self):
        return self._n_seeds_used

    def propose(self, n):
        if type(n) is not int or n < 0:
            raise ValueError("Proposal count must be a nonnegative integer")
        count = min(n, self.n_seeds_remaining)
        end = self._n_seeds_used + count
        configs = deepcopy(self._seed_configs[self._n_seeds_used:end])
        # Queue consumption is committed only after any base proposals succeed.
        if n > count:
            configs.extend(self._base.propose(n - count))
        self._n_seeds_used = end
        return configs

    def observe(self, trial):
        self._base.observe(trial)

    def validate_study_context(self, study_name, maximize):
        if self._selection is not None:
            context = self._selection["context"]
            if (context["study_id"] != study_name
                    or (context["direction"] == "maximize") != maximize):
                raise ValueError("Study identity/objective differs from the warm-start target")

    def state_dict(self):
        body = {"kind": "warm_start", "schema_version": 2,
                "space_signature": space_signature(self.space),
                "seed_configs": deepcopy(self._seed_configs), "selection": deepcopy(self._selection),
                "n_seeds_used": self._n_seeds_used, "n_seeds_total": len(self._seed_configs),
                "seed_queue": deepcopy(self._seed_configs[self._n_seeds_used:]),
                "base_type": type(self._base).__module__ + "." + type(self._base).__qualname__,
                "fallback_reason": self.fallback_reason, "base": deepcopy(self._base.state_dict())}
        return {**body, "binding": checkpoint_digest(body)}

    def load_state_dict(self, state):
        if not isinstance(state, dict) or state.get("kind") != "warm_start":
            raise ValueError(f"WarmStartSearcher cannot load state of kind {state.get('kind') if isinstance(state, dict) else None!r}")
        body = {k: v for k, v in state.items() if k != "binding"}
        if state.get("binding") != checkpoint_digest(body) or state.get("schema_version") != 2:
            raise ValueError("Malformed warm-start checkpoint binding/schema")
        if (state["space_signature"] != space_signature(self.space)
                or state["base_type"] != type(self._base).__module__ + "." + type(self._base).__qualname__):
            raise ValueError("Warm-start checkpoint identity differs")
        candidate = WarmStartSearcher(deepcopy(self._base), state["seed_configs"], selection=state["selection"])
        cursor, total = state["n_seeds_used"], state["n_seeds_total"]
        if (type(cursor) is not int or type(total) is not int or total != len(candidate._seed_configs)
                or not 0 <= cursor <= total or state["seed_queue"] != candidate._seed_configs[cursor:]):
            raise ValueError("Malformed warm-start checkpoint cursor/queue")
        if self._selection is not None and state["selection"] != self._selection:
            raise ValueError("Warm-start selection/context differs")
        candidate._base.load_state_dict(deepcopy(state["base"]))
        self._base, self._seed_configs, self._selection = candidate._base, candidate._seed_configs, candidate._selection
        self._n_seeds_used = cursor
        self.fallback_reason = state["fallback_reason"]

    @property
    def support(self):
        from dataclasses import replace
        base = getattr(self._base, 'support', None)
        return replace(base, joint_batch=False) if base else None

    @property
    def capabilities(self):
        return {**self._base.capabilities, **(self.support.report() if self.support else {})}


class RankedWarmStartSearcher(BaseSearcher):
    """Modern Study-compatible seed proposals with a source-bound selection."""
    def __init__(self, base, selection):
        if not isinstance(base, BaseSearcher):
            raise TypeError("Ranked warm start requires a BaseSearcher")
        if base.history or base.trials:
            raise ValueError("Ranked warm start requires a fresh target base searcher")
        _validate_selection(selection, base.search_space)
        super().__init__(base.search_space, base.seed)
        self._base = base
        self._selection = deepcopy(selection)
        self._queue = SeedQueue(selection)
        self._maximize = selection["context"]["direction"] == "maximize"
        if hasattr(base, "maximize") and base.maximize != self._maximize:
            raise ValueError("Base searcher and target objective direction differ")

    @classmethod
    def from_store(cls, base, store, *, context, n=10):
        if context is None:
            raise ValueError("An explicit target context is required")
        return cls(base, load_seed_selection(store, base.search_space, context=context, n=n))

    @property
    def maximize(self):
        return self._maximize

    @maximize.setter
    def maximize(self, value):
        if not isinstance(value, bool) or value != self._maximize:
            raise ValueError("Study objective direction differs from warm-start context")

    @property
    def support(self):
        from dataclasses import replace
        base = getattr(self._base, 'support', None)
        return replace(base, joint_batch=False) if base else None

    @property
    def capabilities(self):
        return {**self._base.capabilities, **(self.support.report() if self.support else {})}

    @property
    def selection(self):
        return deepcopy(self._selection)

    @property
    def n_seeds_used(self):
        return self._queue.state_dict()["cursor"]

    @property
    def n_seeds_remaining(self):
        return len(self._selection["seeds"]) - self.n_seeds_used

    @property
    def fallback_reason(self):
        return "no_eligible_history" if not self._selection["seeds"] else None

    def suggest(self):
        seeds = self._queue.take(1)
        return Config(seeds[0]) if seeds else self._base.suggest()

    def validate_study_context(self, study_name):
        if study_name != self._selection["context"]["study_id"]:
            raise ValueError("Study identity differs from the held-out warm-start target")

    def observe(self, result):
        # Transfer only current-study config identities and actual measurements.
        self._base.trials = deepcopy(self.trials)
        self._base.observe(result)
        super().observe(result)

    def get_state(self):
        body = {**deepcopy(super().get_state()), "kind": "ranked_warm_start_v1",
                "selection": self.selection, "queue": self._queue.state_dict(),
                "space_signature": space_signature(self.search_space),
                "base_type": type(self._base).__module__ + "." + type(self._base).__qualname__,
                "base": deepcopy(self._base.get_state())}
        return {**body, "binding": checkpoint_digest(body)}

    def set_state(self, state):
        if not isinstance(state, dict):
            raise ValueError("Malformed ranked warm-start checkpoint")
        body = {k: v for k, v in state.items() if k != "binding"}
        if state.get("binding") != checkpoint_digest(body) or state.get("kind") != "ranked_warm_start_v1":
            raise ValueError("Malformed ranked warm-start checkpoint binding/schema")
        if (state["selection"] != self._selection
                or state["space_signature"] != space_signature(self.search_space)
                or state["base_type"] != type(self._base).__module__ + "." + type(self._base).__qualname__):
            raise ValueError("Ranked warm-start context, selection or base differs")
        queue = SeedQueue(self._selection)
        queue.load_state_dict(state["queue"])
        base = deepcopy(self._base)
        base.set_state(deepcopy(state["base"]))
        if hasattr(base, "maximize") and base.maximize != self._maximize:
            raise ValueError("Restored base objective differs from warm-start context")
        candidate = BaseState(self.search_space)
        candidate.set_state(deepcopy(state))
        if (_checkpoint_json([r.to_dict() for r in candidate.history]) != _checkpoint_json([r.to_dict() for r in base.history])
                or any(tid not in candidate.trials or config.to_dict() != candidate.trials[tid].to_dict()
                       for tid, config in base.trials.items()) or candidate.seed != base.seed):
            raise ValueError("Base and wrapper current-study histories differ")
        self.seed, self.history, self.trials = candidate.seed, candidate.history, candidate.trials
        self._base, self._queue = base, queue


class BaseState(BaseSearcher):
    """Detached validation of the shared base state before an atomic restore."""
    def suggest(self):
        raise NotImplementedError
