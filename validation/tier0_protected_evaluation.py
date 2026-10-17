"""Select and decode protected incumbents without running PPO.

Selection uses search returns only. Freeze this plan before any test episode;
test values never choose the incumbent or enter searcher.observe. The rank
campaign verifies artifacts and runs the evaluator; these utilities alone
cannot certify a run.
"""

from __future__ import annotations

import math

from validation.tier0_analysis import training_seed
from validation.tier0_design import canonical_digest, study_stream_slot


def protected_seed(stream_slot, observation_index, episodes):
    """Reserve [10000,100000) inside each existing 2**17 study namespace.

    Training uses offsets 0..9999. Search evaluation starts at 100000.
    Count every episode, not merely the initial seed, when checking collisions.
    Matching task/block/observation indices across paired arms share test seeds.
    """
    if type(observation_index) is not int or type(episodes) is not int or episodes < 1:
        raise ValueError("Integer observation index and positive episode count required")
    training_seed(stream_slot, observation_index)  # Existing range validation.
    offset = 10000 + observation_index * episodes
    if offset + episodes > 100000:
        raise ValueError("Protected episodes exceed reserved study namespace")
    return stream_slot * 131072 + offset


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def freeze_incumbent_plan(design, record, *, allow_incomplete=False):
    """Bind a complete search trace and select each grid incumbent before tests.

    All policy selection is based on the maximize-return search score; equal
    scores retain the earliest delivered incumbent. Policy evaluation cost is
    additional to search budget and must be included in the resource request.
    Complete accounted traces are the default. The rank adapter may explicitly
    preserve a failed trace's verified prefix, leaving the suffix unresolved.
    """
    task = design["tasks"][record["task"]]
    if record.get("design_digest") != canonical_digest(design):
        raise ValueError("Search trace belongs to a different design")
    budget = task["budget"]["seconds"]
    slot = study_stream_slot(design, record["task"], record["seed"])
    episodes = task["settings"]["eval_episodes"]
    status = record.get("status")
    incomplete = allow_incomplete and status in {"failed", "trial_limit"}
    if (not _finite(budget) or budget <= 0 or record.get("budget_seconds") != budget
            or record.get("rng_stream_slot") != slot or (status != "complete" and not incomplete)
            or record.get("accounting_complete") is not True):
        raise ValueError("Complete accounted search with the frozen budget/stream required")
    elapsed = record.get("elapsed_seconds")
    if not _finite(elapsed) or elapsed < 0 or (not incomplete and elapsed < budget):
        raise ValueError("Search trace must account through the budget")
    observations = record["observations"]
    limit = task["budget"]["trial_limit"]
    if type(limit) is not int or limit < 1 or len(observations) > limit:
        raise ValueError("Trial safety count exceeded")
    protected_seed(slot, limit - 1, episodes)  # Validate the whole reservation.
    grid = design["budget_grid"]
    if (len(grid) < 2 or any(not _finite(x) for x in grid)
            or grid[0] != 0 or grid[-1] != 1
            or any(a >= b for a, b in zip(grid, grid[1:]))):
        raise ValueError("Invalid frozen budget grid")
    last = 0.0
    for index, observation in enumerate(observations):
        when, value = observation["completed_seconds"], observation["value"]
        if (observation.get("index") != index or observation.get("training_seed") != training_seed(slot, index)
                or not _finite(when) or when <= last or when > elapsed or not _finite(value)):
            raise ValueError("Invalid ordered search observation")
        reference = observation.get("artifact_refs", {}).get("checkpoint", {})
        if (not isinstance(reference.get("path"), str) or not reference["path"]
                or not isinstance(reference.get("sha256"), str)
                or len(reference["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in reference["sha256"])):
            raise ValueError("Every search policy needs a checkpoint hash binding")
        last = when
    indices = []
    unknown = []
    # For an unclassified interruption, only the prefix through the last
    # delivered observation is used. A failed call may have unfinished output;
    # do not pretend elapsed time alone proves no policy could have arrived.
    prefix = last if incomplete else budget
    for fraction in grid:
        unresolved = fraction * budget > prefix
        unknown.append(unresolved)
        available = [i for i, observation in enumerate(observations)
                     if observation["completed_seconds"] <= fraction * budget]
        indices.append(max(available, key=lambda i: observations[i]["value"]) if available and not unresolved else None)
    evaluations = [
        {"observation_index": index, "checkpoint": dict(observations[index]["artifact_refs"]["checkpoint"]),
         "seed": protected_seed(slot, index, episodes), "episodes": episodes}
        for index in sorted({i for i in indices if i is not None})
    ]
    return {"kind": "protected-incumbent-evaluation-plan", "schema_version": 1,
            "design_digest": canonical_digest(design), "search_trace_digest": canonical_digest(record),
            "task": record["task"], "seed": record["seed"], "arm": record["arm"], "entry": record["entry"],
            "budget_grid": list(grid), "incumbent_indices": indices, "evaluations": evaluations,
            "unknown_grid": unknown, "trace_status": status,
            "selection": "search_score_only_earliest_tie_no_future_observations",
            "timing": "All search traces and this plan frozen before protected evaluation",
            "feeds_searcher": False, "certifies_acceptance": False}


def protected_curve(plan, receipts):
    """Reconstruct test scores at search-selected policies, with no reselection.

    Missing/nonfinite test results remain unknown. Episode failures cannot be
    silently removed before averaging. The caller must also validate hashes of
    policy/recipe/receipt files and final protocol identity; no artifact is loaded
    or executed here. A claimed receipt hash is not by itself authentic evidence.
    """
    if (plan.get("kind") != "protected-incumbent-evaluation-plan"
            or plan.get("schema_version") != 1 or plan.get("feeds_searcher") is not False
            or plan.get("selection") != "search_score_only_earliest_tie_no_future_observations"):
        raise ValueError("Unknown frozen protected evaluation plan")
    expected = {item["observation_index"]: item for item in plan["evaluations"]}
    if len(expected) != len(plan["evaluations"]):
        raise ValueError("Duplicate policy in frozen evaluation plan")
    values = {}
    for receipt in receipts:
        index = receipt["observation_index"]
        if index not in expected or index in values:
            raise ValueError("Duplicate or unselected protected policy")
        spec = expected[index]
        if (receipt.get("plan_digest") != canonical_digest(plan)
                or receipt.get("checkpoint_sha256") != spec["checkpoint"]["sha256"]
                or receipt.get("seed") != spec["seed"]):
            raise ValueError("Protected receipt differs from frozen plan, policy or seed")
        returns = receipt["returns"]
        if not isinstance(returns, list) or len(returns) != spec["episodes"]:
            raise ValueError("All planned test episodes must remain present")
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)))
               for value in returns):
            raise ValueError("Malformed test episode is an integrity error, not missing data")
        # Divide before summing to avoid overflowing a finite arithmetic mean.
        values[index] = ((True, math.fsum(value / len(returns) for value in returns))
                         if all(_finite(value) for value in returns) else None)
    curve = []
    unknown = plan.get("unknown_grid", [False] * len(plan["incumbent_indices"]))
    if len(unknown) != len(plan["incumbent_indices"]) or any(type(value) is not bool for value in unknown):
        raise ValueError("Invalid unresolved-prefix mask")
    for index, unresolved in zip(plan["incumbent_indices"], unknown, strict=True):
        if index is not None and index not in expected:
            raise ValueError("Incumbent missing from frozen evaluation plan")
        if unresolved and index is not None:
            raise ValueError("An unresolved grid point cannot select a known policy")
        curve.append(None if unresolved else (False, None) if index is None else values.get(index))
    return curve
