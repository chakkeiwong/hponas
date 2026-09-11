"""
⚠️ OLD CODE - DO NOT USE IN NEW IMPLEMENTATIONS ⚠️
This file is LEGACY code from pre-recovery implementation.
- Used only by validation scripts
- Contains specification violations: builds RGPE immediately (WRONG per TRACEABILITY_MATRIX_v1.md)
- Correct implementation should defer RGPE until sufficient data

Warm start: seed searchers from prior run-store trials.

Survey reference: Ch 8 sec:warm-start-from-store, validation V12.
Tier 1: Implement config seeding from ranked prior trials with space compatibility checks.
Tier 2: V12 gate requires ≥20% trial savings (measured campaign), persistent store,
        crash recovery, monitoring.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional, Sequence

from .space import SearchSpace

if TYPE_CHECKING:
    from .store import Store


def load_seed_configs(
    store: Store,
    study_id: str,
    target_space: SearchSpace,
    n: int = 10,
    objective: str = "minimize",
) -> list[dict]:
    """
    Load seed configurations from a prior study's best trials.

    Args:
        store: Run store instance
        study_id: Prior study to load from
        target_space: Search space for the new study (for compatibility check)
        n: Number of top trials to load (default: 10)
        objective: "minimize" or "maximize"

    Returns:
        List of compatible configurations, sorted best-first (empty if none compatible).

    Survey: V12 warm start loads ranked trials from a prior study. Configs are filtered
    through the target space's validate_config to ensure type/bounds compatibility.
    If the source and target spaces differ structurally (conditional knobs, added/removed
    knobs), incompatible configs are skipped silently — warm start is best-effort.

    Usage:
        store = Store("runs.db")
        seeds = load_seed_configs(store, "prior_study_1", target_space, n=5)
        # Seeds can be passed to searcher initialization or used as initial trials
    """
    study = store.read_study(study_id)
    if study is None:
        return []

    # Get ranked trials from the store
    trials = store.get_best_trials(study_id, n=n, objective=objective)
    if not trials:
        return []

    # Filter through target space validation (skip incompatible configs)
    compatible = []
    for trial in trials:
        try:
            target_space.validate_config(trial.config)
            compatible.append(trial.config)
        except (ValueError, KeyError):
            # Config doesn't match target space structure/bounds — skip
            continue

    return compatible


def check_space_compatibility(
    source_space_json: str,
    target_space: SearchSpace,
) -> bool:
    """
    Check if a source space (serialized) is structurally compatible with a target space.

    Args:
        source_space_json: JSON-serialized SearchSpace from store
        target_space: The new study's space

    Returns:
        True if spaces have the same knob structure (names, kinds, bounds), False otherwise.

    Survey: Tier 2 cross-study warm start may query trials from multiple prior studies.
    Structural compatibility (same knob names and kinds) is a stricter filter than
    per-config validation. Use this to short-circuit incompatible studies before loading
    trials.

    Note: This is a Tier 2 optimization. Tier 1 just validates configs on load.
    """
    try:
        source_space = SearchSpace.from_json(source_space_json)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        # Unparseable or legacy (pre-canonical-JSON) space record: treat as incompatible
        # rather than raising. Warm start is best-effort; a study we cannot read is a
        # study we skip.
        return False

    # Compare kind and bounds per knob name. Bounds are normalized to tuples on both
    # sides: a JSON round-trip turns continuous/ordinal (low, high) into [low, high],
    # so comparing raw values would report every space as incompatible with itself.
    source_knobs = {k.name: (k.kind, tuple(k.bounds)) for k in source_space.knobs}
    target_knobs = {k.name: (k.kind, tuple(k.bounds)) for k in target_space.knobs}

    if set(source_knobs) != set(target_knobs):
        return False

    return all(source_knobs[name] == target_knobs[name] for name in source_knobs)


def load_seed_configs_from_all_studies(
    store: Store,
    target_space: SearchSpace,
    n: int = 10,
    objective: str = "minimize",
    exclude_study_ids: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """
    Load seed configs from every structurally compatible study in the store.

    Survey: V12 warm start queries "similar completed studies" — plural. This pools the
    best trials across studies whose space matches the target structurally, then re-ranks
    the pool globally and returns the top n.

    Args:
        store: Run store instance
        target_space: Search space for the new study
        n: Number of seed configs to return overall (not per study)
        objective: "minimize" or "maximize"
        exclude_study_ids: Studies to skip (e.g. the study being started)

    Returns:
        Up to n configs, best-first, deduplicated.

    Comparability caveat: values are pooled across studies, which assumes the studies
    optimized the same objective on the same workload. `check_space_compatibility` only
    proves the *space* matches; matching spaces do not prove matching objectives. Callers
    pooling across workloads should filter study ids themselves.
    """
    excluded = set(exclude_study_ids or ())
    scored: list[tuple[float, dict[str, Any]]] = []

    for study in store.list_studies():
        if study.study_id in excluded:
            continue
        if study.objective != objective:
            continue
        if not check_space_compatibility(study.space_json, target_space):
            continue

        for trial in store.get_best_trials(study.study_id, n=n, objective=objective):
            if trial.value is None:
                continue
            try:
                target_space.validate_config(trial.config)
            except (ValueError, KeyError):
                continue
            scored.append((trial.value, trial.config))

    scored.sort(key=lambda pair: pair[0], reverse=(objective == "maximize"))

    # Deduplicate, keeping the best-ranked occurrence of each config
    seen: set[str] = set()
    seeds: list[dict[str, Any]] = []
    for _, config in scored:
        key = json.dumps(config, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        seeds.append(config)
        if len(seeds) >= n:
            break

    return seeds


class WarmStartSearcher:
    """
    Wrap any Searcher so its first proposals are seed configs from prior studies.

    Survey reference: Ch 8 sec:warm-start-from-store, roadmap-11 / ch08-03 (validation V12).

    The wrapper drains a queue of seed configs before delegating to the base searcher, so
    the early budget goes to configurations that already worked somewhere rather than to
    the base searcher's cold-start design. Everything else — observations, capabilities —
    passes straight through.

    Seeds are *proposed*, not injected as observations. Their prior objective values are
    not comparable across workloads, and feeding them to the base searcher's surrogate as
    if they were measurements of the current study would bias it toward whatever the
    earlier study happened to measure. The base searcher learns from the seeds the normal
    way: `observe` is called once they have actually been evaluated here.

    Tier 1 scope: implementation plus unit tests. The V12 gate (warm start saves ≥20% of
    trials) is a Tier 2 measured campaign.

    Usage:
        base = SobolSearcher(space, seed=0)
        seeds = load_seed_configs(store, "prior_study", space, n=5)
        searcher = WarmStartSearcher(base, seeds)
        first = searcher.propose(3)   # seeds[0:3]
    """

    def __init__(self, base: Any, seed_configs: Sequence[dict[str, Any]]):
        self._base = base
        self._seed_queue: list[dict[str, Any]] = [dict(c) for c in seed_configs]
        self._n_seeds_total = len(self._seed_queue)
        self._n_seeds_used = 0

    @classmethod
    def from_store(
        cls,
        base: Any,
        store: Store,
        space: SearchSpace,
        study_id: Optional[str] = None,
        n: int = 10,
        objective: str = "minimize",
    ) -> "WarmStartSearcher":
        """
        Build a warm-started searcher directly from the run store.

        With `study_id`, seeds come from that study alone; without it, from every
        compatible study in the store. Either way an empty store degrades to the base
        searcher's cold-start behavior rather than failing.
        """
        if study_id is not None:
            seeds = load_seed_configs(store, study_id, space, n=n, objective=objective)
        else:
            seeds = load_seed_configs_from_all_studies(
                store, space, n=n, objective=objective
            )
        return cls(base, seeds)

    @property
    def n_seeds_remaining(self) -> int:
        """Seed configs not yet proposed."""
        return len(self._seed_queue)

    @property
    def n_seeds_used(self) -> int:
        """Seed configs already handed out (V12 accounting)."""
        return self._n_seeds_used

    def propose(self, n: int) -> list[dict[str, Any]]:
        """
        Propose n configs: queued seeds first, then base-searcher proposals.

        The base searcher is only asked for the shortfall, so consuming seeds does not
        advance its internal sequence — a warm-started Sobol run and a cold one draw the
        same Sobol points, just offset by the number of seeds spent.
        """
        if n <= 0:
            return []

        n_from_seeds = min(n, len(self._seed_queue))
        configs = [self._seed_queue.pop(0) for _ in range(n_from_seeds)]
        self._n_seeds_used += n_from_seeds

        shortfall = n - n_from_seeds
        if shortfall > 0:
            configs.extend(self._base.propose(shortfall))

        return configs

    def observe(self, trial: dict[str, Any]) -> None:
        """Pass the observation through to the base searcher."""
        self._base.observe(trial)

    def state_dict(self) -> dict[str, Any]:
        """Serialize wrapper state plus the base searcher's state (crash recovery)."""
        return {
            "kind": "warm_start",
            "seed_queue": [dict(c) for c in self._seed_queue],
            "n_seeds_total": self._n_seeds_total,
            "n_seeds_used": self._n_seeds_used,
            "base": self._base.state_dict(),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """
        Restore wrapper and base state after a crash.

        The unconsumed seed queue is restored verbatim so recovery does not re-propose
        seeds that were already evaluated (the store would have them as duplicate trials).
        """
        if state.get("kind") != "warm_start":
            raise ValueError(
                f"WarmStartSearcher cannot load state of kind {state.get('kind')!r}"
            )
        self._seed_queue = [dict(c) for c in state["seed_queue"]]
        self._n_seeds_total = int(state["n_seeds_total"])
        self._n_seeds_used = int(state["n_seeds_used"])
        self._base.load_state_dict(state["base"])

    @property
    def capabilities(self) -> dict[str, Any]:
        """Delegate to the base searcher — warm start adds no capability of its own."""
        return self._base.capabilities
