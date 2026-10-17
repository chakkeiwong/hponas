"""Exact within-study ranks and immutable warm-start selections.

Only configurations transfer. Objective measurements remain in their original
studies. Store snapshots carry explicit task, objective and endpoint identity.
"""
from bisect import bisect_left, bisect_right
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math

from hponas.encoding import as_knob_space


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def space_signature(space):
    """Include coordinate transforms, conditional predicates and category order."""
    return digest([{key: knob.to_dict()[key] for key in
                    ["name", "kind", "bounds", "transform", "condition"]}
                   for knob in as_knob_space(space).knobs])


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _identity(record):
    if not isinstance(record, dict):
        raise ValueError("History identity must be an object")
    for field in ["study_id", "task_id", "model_family", "task_domain", "objective_key"]:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError("Missing explicit history identity: " + field)
    if record.get("direction") not in {"minimize", "maximize"}:
        raise ValueError("Invalid objective direction")


def physical_key(space, config):
    space = as_knob_space(space)
    space.validate_config(config)
    values = deepcopy(config)
    for knob in space.knobs:
        if knob.name in values and knob.kind == "continuous":
            values[knob.name] = float(values[knob.name])
            if values[knob.name] == 0:
                values[knob.name] = 0.0
    return canonical(values)


def select(histories, target, space, limit):
    """Select exact empirical mid-distribution ranks within eligible studies."""
    histories = list(histories)
    _identity(target)
    if not _finite(target.get("history_cutoff")):
        raise ValueError("An explicit finite history cutoff is required")
    if type(limit) is not int or limit < 0:
        raise ValueError("Selection limit must be a nonnegative integer")
    if not _finite(target.get("endpoint_fidelity")) or target["endpoint_fidelity"] <= 0:
        raise ValueError("A positive finite endpoint fidelity is required")
    expected_space = space_signature(space)
    if target.get("space_signature") != expected_space:
        raise ValueError("Target context and actual space differ")
    held_out = target.get("excluded_task_ids")
    if (not isinstance(held_out, list) or any(not isinstance(v, str) for v in held_out)
            or target["task_id"] not in held_out):
        raise ValueError("Explicit held-out target-task exclusion is required")
    context = deepcopy(target)
    history_ids, ranked, exclusions = set(), [], []
    for study in histories:
        _identity(study)
        sid = study["study_id"]
        if sid in history_ids:
            raise ValueError("Duplicate historical study identity")
        history_ids.add(sid)
        reason = None
        if sid == target["study_id"] or study["task_id"] in held_out:
            reason = "held_out"
        elif study.get("status") != "completed":
            reason = "incomplete_study"
        elif not _finite(study.get("completed_at")) or study["completed_at"] > target["history_cutoff"]:
            reason = "outside_history_cutoff"
        else:
            for key in ["model_family", "task_domain", "objective_key", "direction", "space_signature", "endpoint_fidelity"]:
                if study.get(key) != target[key]:
                    reason = "incompatible_" + key
                    break
        if reason:
            exclusions.append({"study_id": sid, "reason": reason})
            continue
        trial_ids, eligible = set(), []
        for trial in study["trials"]:
            tid = trial.get("trial_id")
            if not isinstance(tid, str) or not tid or tid in trial_ids:
                raise ValueError("Missing or duplicated historical trial identity")
            trial_ids.add(tid)
            if (trial.get("status") != "completed" or not _finite(trial.get("value"))
                    or trial.get("fidelity") != target["endpoint_fidelity"]):
                continue
            try:
                key = physical_key(space, trial["config"])
            except (ValueError, KeyError, TypeError):
                continue
            score = trial["value"] if target["direction"] == "minimize" else -trial["value"]
            eligible.append((score, tid, deepcopy(trial["config"]), key))
        ordered = sorted(row[0] for row in eligible)
        for score, tid, config, key in eligible:
            # (# strictly better + half of ties) / N. No cross-study raw scale.
            numerator = bisect_left(ordered, score) + bisect_right(ordered, score)
            quantile = Fraction(numerator, 2*len(ordered))
            ranked.append({"study_id": sid, "trial_id": tid, "config": config,
                           "quantile": [quantile.numerator, quantile.denominator], "key": key})
    ranked.sort(key=lambda r: (Fraction(*r["quantile"]), r["study_id"], r["trial_id"]))
    selected, seen = [], set()
    for row in ranked:
        if len(selected) >= limit:
            break
        key = row["key"]
        if key not in seen:
            selected.append({k: v for k, v in row.items() if k != "key"})
            seen.add(key)
    body = {"schema": "ranked_history_v1", "context": context, "limit": limit,
            "seeds": selected, "excluded": sorted(exclusions, key=lambda r: r["study_id"]),
            "history_bindings": sorted([{"study_id": s["study_id"], "sha256": s["binding"]}
                                        for s in histories if "binding" in s], key=lambda r: r["study_id"])}
    return {**body, "binding": digest(body)}


def target_context(space, *, study_id, task_id, model_family, task_domain,
                   objective_key, direction, history_cutoff, endpoint_fidelity=1.0,
                   excluded_task_ids=()):
    """Declare the target before retrieving any historical outcomes."""
    context = {"study_id": study_id, "task_id": task_id, "model_family": model_family,
               "task_domain": task_domain, "objective_key": objective_key,
               "direction": direction, "history_cutoff": history_cutoff,
               "endpoint_fidelity": endpoint_fidelity, "space_signature": space_signature(space),
               "excluded_task_ids": sorted(set([task_id, *excluded_task_ids]))}
    select([], context, space, 0)
    return context


class SeedQueue:
    """Immutable selection binding plus a recoverable consumption cursor.

    Only configurations are proposed. Current-study observations remain owned
    by the actual base searcher; this object has no observe or surrogate API.
    """
    def __init__(self, selection):
        body = {k: v for k, v in selection.items() if k != "binding"}
        if selection.get("binding") != digest(body):
            raise ValueError("Selection bytes differ from their binding")
        self._selection = deepcopy(selection)
        self._cursor = 0

    def take(self, count):
        if type(count) is not int or count < 0:
            raise ValueError("Proposal count must be a nonnegative integer")
        seeds = self._selection["seeds"]
        end = min(self._cursor+count, len(seeds))
        result = [deepcopy(row["config"]) for row in seeds[self._cursor:end]]
        self._cursor = end
        return result

    def state_dict(self):
        return {"schema": "ranked_seed_queue_v1", "selection_binding": self._selection["binding"],
                "cursor": self._cursor}

    def load_state_dict(self, state):
        if (not isinstance(state, dict) or set(state) != {"schema", "selection_binding", "cursor"}
                or state["schema"] != "ranked_seed_queue_v1"
                or state["selection_binding"] != self._selection["binding"]
                or type(state["cursor"]) is not int or not 0 <= state["cursor"] <= len(self._selection["seeds"])):
            raise ValueError("Incompatible or malformed seed queue checkpoint")
        self._cursor = state["cursor"]
