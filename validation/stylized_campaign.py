"""Finite known-answer conformance, with descriptive (never gated) search regret.

The frozen corpus is deliberately exposed. Replay establishes method/seed
identity, not an independent proof of a search algorithm's quality. Numerical
outputs are checked by separate analytic/intermediate-output oracles.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
import math
from pathlib import Path
import signal
import time

from hponas import Config, GPSearcher, Knob, RandomSearcher, Result, SearchSpace, SobolSearcher
from hponas.encoding import SpaceEncoder
from hponas.persistence import atomic_json
from validation.evidence import ROOT, digest, source_digest
from validation.stylized_reference import optimum, verify_observation
from validation.stylized_contract import STYLIZED_POLICY
from workloads.stylized import case_specs, evaluate, validate_config

CLAIM = STYLIZED_POLICY["claim"]
SEEDS = STYLIZED_POLICY["seeds"]
TRIALS = STYLIZED_POLICY["trials_per_study"]
INITIAL = 5
METHODS = {"V04-T0": ["random", "sobol", "gp", "tpe"],
           "V05": ["gp_log", "gp_linear"]}
LIMITS = STYLIZED_POLICY["generation_wall_seconds"]


def contract(entry):
    if entry not in METHODS:
        raise ValueError("Unknown stylized entry")
    return {"schema_version": 1, "claim": CLAIM, "entry": entry,
            "cases": [c for c in case_specs() if entry == "V04-T0" or c["family"] == "ridge"],
            "methods": METHODS[entry], "seeds": SEEDS, "trials": TRIALS,
            "gp_options": {"initial_random_samples": INITIAL, "num_restarts": 2},
            "initialization": "shared_physical_prefix_v1" if entry == "V05" else "method_native",
            "wall_limit_seconds": LIMITS[entry], "threads": 1, "gpu": False,
            "verdict": "all_fixed_slots_and_probes_conform_no_regret_threshold",
            "numerics": "binary64_gamma4096_condition_scaled_engineering_envelope",
            "missingness": "retain_all_slots_no_replacement_incomplete_is_inconclusive",
            "scope": "exposed_finite_corpus_no_method_ranking_or_default_recommendation"}


def freeze(entry, run_dir):
    return {"contract": contract(entry), "source_digest": source_digest(),
            "protocol_sha256": digest(ROOT / "validation/protocols" /
                                      f"{entry.lower().replace('-', '_')}_protocol.md"),
            "registry_sha256": digest(ROOT / "validation/protocols.json"),
            "run_dir": str(Path(run_dir).resolve())}


def initial_configs(case, seed):
    """Fixed physical prefix; neither coordinate arm samples its own prefix.

    Coprime modular fractions give reproducible interior coverage without an
    RNG or a workload optimum. Log spacing is part of the declared design.
    """
    return [{k["name"]: math.exp(math.log(k["bounds"][0]) +
                                ((seed + 37*i + 19*j) % 101 + .5)/101 *
                                math.log(k["bounds"][1]/k["bounds"][0]))
             for j, k in enumerate(case["space"])} for i in range(INITIAL)]


def make_searcher(case, method, seed):
    space = SearchSpace([Knob(k["name"], k["kind"], tuple(k["bounds"]),
                             transform="none" if method == "gp_linear" else k["transform"])
                         for k in case["space"]])
    if method.startswith("gp"):
        return GPSearcher(space, seed=seed, maximize=False,
                          initial_random_samples=INITIAL, num_restarts=2)
    if method == "random":
        return RandomSearcher(space, seed=seed)
    if method == "sobol":
        return SobolSearcher(space, seed=seed)
    if method == "tpe":
        from hponas.searchers.adapter import LegacySearcherAdapter
        from hponas.searchers_tpe import TPESearcher
        return LegacySearcherAdapter(TPESearcher(space, seed=seed), maximize=False)
    raise ValueError("Unknown method")


def _proposal(searcher, prefix, index):
    if index < len(prefix):
        searcher.n_suggestions += 1
        return Config(copy.deepcopy(prefix[index]))
    return searcher.suggest()


def _observe(searcher, index, config, observation):
    tid = str(index)
    searcher.trials[tid] = config
    searcher.observe(Result(tid, observation["value"], cost=float(observation["work_units"])))


def slots(spec):
    for case in spec["cases"]:
        for seed_index, seed in enumerate(spec["seeds"]):
            methods = spec["methods"]
            offset = seed_index % len(methods)
            for method in methods[offset:] + methods[:offset]:
                yield case, seed, method


def probes(case):
    if case["family"] == "bottleneck":
        return [{"width": h} for h in range(1, 5)]
    configs = [optimum(case)["config"]]
    for u in [0., .5, 1.]:
        configs.append({k["name"]: k["bounds"][0]+u*(k["bounds"][1]-k["bounds"][0])
                        for k in case["space"]})
    return configs


@contextmanager
def bounded_seconds(seconds):
    """Bound this local Linux main-process phase, including acquisition fits."""
    def expired(signum, frame):
        raise TimeoutError("Stylized phase wall limit reached")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer[0]:
        raise ValueError("Stylized phase cannot replace an existing process timer")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_study(entry, case, seed, method):
    """Retain partial observations on failure; never substitute a seed."""
    record = {"case": case["id"], "seed": seed, "method": method,
              "status": "complete", "observations": [], "selected_index": None}
    started = time.monotonic()
    try:
        searcher = make_searcher(case, method, seed)
        prefix = initial_configs(case, seed) if entry == "V05" else []
        for index in range(TRIALS):
            before = time.monotonic()
            config = _proposal(searcher, prefix, index)
            suggested = time.monotonic()
            validate_config(case, config.values)
            observation = evaluate(case["id"], config.values)
            evaluated = time.monotonic()
            coordinates = SpaceEncoder(searcher.search_space).encode(config).tolist()
            decoded = SpaceEncoder(searcher.search_space).decode(coordinates)
            _observe(searcher, index, config, observation)
            record["observations"].append({"index": index, "config": config.values,
                "coordinates": coordinates, "decoded": decoded, "observation": observation,
                "search_seconds": suggested-before, "objective_seconds": evaluated-suggested})
        record["selected_index"] = int(searcher.get_best(maximize=False).trial_id)
    except Exception as exc:
        record.update(status="incomplete" if isinstance(exc, TimeoutError) else "failed",
                      error=f"{type(exc).__name__}: {exc}")
    record["elapsed_seconds"] = time.monotonic()-started
    return record


def _binding(path):
    return {"path": str(path.resolve()), "sha256": digest(path)}


def campaign(entry, run_dir):
    run_dir = Path(run_dir).resolve()
    spec = contract(entry)
    # This immutable local manifest precedes objective calls. Local chronology
    # is trusted; there is no claim of remote attestation or blinded fixtures.
    manifest = run_dir / "stylized-freeze.json"
    if manifest.exists():
        raise ValueError("Refusing to overwrite an existing stylized freeze")
    atomic_json(manifest, freeze(entry, run_dir))
    probe_records = [{"case": c["id"], "config": config,
                      "observation": evaluate(c["id"], config)}
                     for c in spec["cases"] for config in probes(c)]
    probe_file = run_dir / "reference-probes.json"
    atomic_json(probe_file, probe_records)
    trace_file = run_dir / "traces.jsonl"
    exhausted = False
    with trace_file.open("x") as output:
        with bounded_seconds(spec["wall_limit_seconds"]):
            for case, seed, method in slots(spec):
                if exhausted:
                    record = {"case": case["id"], "seed": seed, "method": method,
                              "status": "incomplete", "error": "campaign_wall_limit",
                              "observations": [], "selected_index": None, "elapsed_seconds": 0.}
                else:
                    record = run_study(entry, case, seed, method)
                    exhausted = record["status"] == "incomplete"
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
    result = {"schema_version": 4, "validation_id": entry, "claim": CLAIM,
              "run_dir": str(run_dir), "freeze": _binding(manifest),
              "probes": _binding(probe_file), "traces": _binding(trace_file)}
    # The decision layer replays proposals and independently reconstructs all
    # raw numerical outputs; this first summary does not claim method identity.
    records = [json.loads(line) for line in trace_file.read_text().splitlines()]
    result["summary"] = reconstruct(spec, records, probe_records, replay=False)
    return result


def _seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid measured duration")
    return value


def verify_coordinates(case, method, row):
    """Reference forward/inverse formulas, independent of SpaceEncoder."""
    coordinates = row["coordinates"]
    if not isinstance(coordinates, list) or len(coordinates) != len(case["space"]):
        raise ValueError("Wrong coordinate dimension")
    validate_config(case, row["decoded"])
    for k, u in zip(case["space"], coordinates):
        lo, hi = k["bounds"]
        x = row["config"][k["name"]]
        log = k["transform"] == "log" and method != "gp_linear"
        expected = math.log(x/lo)/math.log(hi/lo) if log else (x-lo)/(hi-lo)
        if (type(u) not in (int, float) or not math.isfinite(u)
                or not math.isclose(u, expected, rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(row["decoded"][k["name"]], x, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Forward/inverse coordinates disagree with physical configuration")


def reconstruct(spec, records, probe_records, *, replay=True):
    planned = list(slots(spec))
    if len(records) != len(planned):
        raise ValueError("Missing or additional study slots")
    expected_probes = [(c, config) for c in spec["cases"] for config in probes(c)]
    if len(probe_records) != len(expected_probes):
        raise ValueError("Missing reference probes")
    failures = []
    for row, (case, config) in zip(probe_records, expected_probes):
        if row["case"] != case["id"] or row["config"] != config:
            raise ValueError("Reference probe identities changed")
        try:
            verify_observation(case, config, row["observation"])
        except (ValueError, KeyError, TypeError) as exc:
            failures.append(f"probe/{case['id']}: {exc}")
    summaries = []
    missing = 0
    for record, (case, seed, method) in zip(records, planned):
        if [record["case"], record["seed"], record["method"]] != [case["id"], seed, method]:
            raise ValueError("Study identities/order differ from the frozen inventory")
        rows = record["observations"]
        status = record["status"]
        if (status not in {"complete", "failed", "incomplete"} or len(rows) > TRIALS
                or (status == "complete" and len(rows) != TRIALS)):
            raise ValueError("Invalid study completeness")
        if status == "failed":
            failures.append(f"{case['id']}/{seed}/{method}: {record.get('error', 'failed')}")
        if status != "complete":
            missing += TRIALS-len(rows)
        elapsed = _seconds(record["elapsed_seconds"])
        search_seconds, objective_seconds, work_units = 0., 0., 0
        best_curve, best_value, selected = [], math.inf, None
        prefix = initial_configs(case, seed) if spec["entry"] == "V05" else []
        searcher = make_searcher(case, method, seed) if replay and rows else None
        for index, row in enumerate(rows):
            if row["index"] != index:
                raise ValueError("Trial indices changed")
            validate_config(case, row["config"])
            verify_coordinates(case, method, row)
            if index < len(prefix) and row["config"] != prefix[index]:
                raise ValueError("Coordinate arms did not share physical initialization")
            if searcher is not None:
                proposal = _proposal(searcher, prefix, index)
                if proposal.values != row["config"]:
                    raise ValueError("Method/seed does not reproduce the proposal trace")
                _observe(searcher, index, proposal, row["observation"])
            try:
                checked = verify_observation(case, row["config"], row["observation"])
            except (ValueError, KeyError, TypeError) as exc:
                failures.append(f"{case['id']}/{seed}/{method}/{index}: {exc}")
                continue
            if row["observation"]["value"] < best_value:
                best_value, selected = row["observation"]["value"], index
            best_curve.append(min(checked["regret"], best_curve[-1] if best_curve else math.inf))
            search_seconds += _seconds(row["search_seconds"])
            objective_seconds += _seconds(row["objective_seconds"])
            work_units += checked["work_units"]
        if status == "complete" and record["selected_index"] != selected:
            raise ValueError("Selected result is not the observed minimum with first-tie rule")
        if search_seconds + objective_seconds > elapsed + 1e-9:
            raise ValueError("Trial durations exceed the measured study lifetime")
        summaries.append({"case": case["id"], "seed": seed, "method": method,
                          "status": status, "completed_trials": len(rows),
                          "known_optimum": optimum(case), "selected_index": selected,
                          "selected_config": rows[selected]["config"] if selected is not None else None,
                          "best_regret_curve": best_curve,
                          "search_seconds": search_seconds, "objective_seconds": objective_seconds,
                          "elapsed_seconds": elapsed, "work_units": work_units})
    return {"verdict": "FAIL" if failures else "INCONCLUSIVE" if any(
        r["status"] != "complete" for r in records) else "PASS",
        "planned_trials": len(planned)*TRIALS, "completed_trials": sum(len(r["observations"]) for r in records),
        "missing_trials": missing, "reference_probes": len(probe_records),
        "failures": failures, "studies": summaries}


def recompute_result(entry, result):
    if (result.get("schema_version") != 4 or result.get("claim") != CLAIM
            or result.get("validation_id") != entry):
        raise ValueError("Wrong stylized result identity")
    run_dir = Path(result["run_dir"]).resolve()
    contents = {}
    for key, name in [("freeze", "stylized-freeze.json"), ("probes", "reference-probes.json"),
                      ("traces", "traces.jsonl")]:
        binding = result[key]
        path = Path(binding["path"])
        if path.resolve() != run_dir / name or path.is_symlink() or digest(path) != binding["sha256"]:
            raise ValueError("Changed or relocated stylized artifact")
        contents[key] = (json.loads(path.read_text()) if key != "traces"
                         else [json.loads(line) for line in path.read_text().splitlines()])
    if contents["freeze"] != freeze(entry, run_dir):
        raise ValueError("Frozen source, protocol, corpus or resource contract changed")
    with bounded_seconds(LIMITS[entry]):
        summary = reconstruct(contract(entry), contents["traces"], contents["probes"])
    if summary != result["summary"]:
        raise ValueError("Reported summary differs from raw reconstruction")
    return summary["verdict"]
