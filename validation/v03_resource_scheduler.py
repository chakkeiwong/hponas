"""Prospective, outcome-blind resource admission for the complete V03 sweep."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import ceil, isfinite
from pathlib import Path
import time


POLICY_PATH = Path(__file__).resolve().parent / "designs/v03_resource_policy.json"


def policy() -> dict:
    result = json.loads(POLICY_PATH.read_text())
    if result.get("kind") != "v03_measured_resource_admission_v1":
        raise ValueError("Unknown V03 resource admission policy")
    if (result["max_workers"], result["high_memory_limit"], result["child_budget_gib"],
            result["fixed_reserve_gib"], result["guard_gib"]) != (24, 8, 52, 8, 64):
        raise ValueError("V03 admission bounds changed")
    if result["high_memory_gib"] != 6.5 or result["regular_memory_gib"] != 2.25:
        raise ValueError("V03 per-job measured bounds changed")
    if result["calibration_controls"] != [
            "hponas.searchers_gp.xǁGPqLogEISearcherǁ_build_acqf__mutmut_2",
            "hponas.searchers_gp.xǁGPqLogEISearcherǁ_build_acqf__mutmut_3"]:
        raise ValueError("V03 calibrated carryover changed")
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_rows(mutants, tests_by_function, duration_by_test, config, resource_policy=None):
    """Freeze all jobs from the population and selected tests, before any outcome."""
    resource_policy = policy() if resource_policy is None else resource_policy
    if len({name for _, name, _ in mutants}) != len(mutants):
        raise ValueError("Duplicate V03 mutant")
    rows = []
    high_files = set(resource_policy["high_memory_test_files"])
    high_functions = set(resource_policy["measured_high_memory_functions"])
    for _, name, _ in mutants:
        name = name.replace("__init__.", "")
        function = name.split("__mutmut_", 1)[0]
        tests = sorted(tests_by_function.get(function, ()))
        if any(test not in duration_by_test for test in tests):
            raise ValueError("Selected V03 test has no measured clean duration")
        if any(not isfinite(duration_by_test[test]) or duration_by_test[test] < 0 for test in tests):
            raise ValueError("Invalid V03 clean duration")
        duration = sum(duration_by_test[test] for test in tests)
        high = (function in high_functions or
                any(test.split("::", 1)[0] in high_files for test in tests))
        rows.append({"mutant": name, "function": function, "tests": tests,
                     "estimated_test_seconds": duration,
                     "cpu_time_limit_seconds": ceil((duration + config.timeout_constant)
                                                    * config.timeout_multiplier * 2),
                     "resource_class": "high_memory" if high else "regular",
                     "reserved_gib": resource_policy["high_memory_gib"] if high
                     else resource_policy["regular_memory_gib"]})
    return sorted(rows, key=lambda row: row["mutant"])


@dataclass
class Admission:
    resource_policy: dict
    pending: dict

    def __init__(self, resource_policy=None):
        self.resource_policy = policy() if resource_policy is None else resource_policy
        self.pending = {}

    def can_submit(self, row):
        values = self.pending.values()
        return (len(self.pending) < self.resource_policy["max_workers"]
                and (row["resource_class"] != "high_memory" or
                     sum(x["resource_class"] == "high_memory" for x in values)
                     < self.resource_policy["high_memory_limit"])
                and sum(x["reserved_gib"] for x in values) + row["reserved_gib"]
                <= self.resource_policy["child_budget_gib"])

    def submit(self, row):
        if row["mutant"] in self.pending or not self.can_submit(row):
            raise ValueError("V03 job exceeds prospective admission")
        self.pending[row["mutant"]] = row

    def complete(self, mutant):
        if mutant not in self.pending:
            raise ValueError("V03 completion has no admitted job")
        self.pending.pop(mutant)


def dispatch(rows, runner, on_result, on_event, resource_policy=None):
    """Run a finite queue through one forkserver; save results before release."""
    queued = sorted(rows, key=lambda row: (-row["estimated_test_seconds"], row["mutant"]))
    if len({row["mutant"] for row in queued}) != len(queued) or any(not row["tests"] for row in queued):
        raise ValueError("Admission requires distinct runnable mutants")
    admission = Admission(resource_policy)
    runner.startup()
    started = time.monotonic()
    count = 0
    try:
        def drain():
            nonlocal count
            result = runner.wait_for_result()
            on_result(result)
            admission.complete(result.mutant_name)
            on_event({"kind": "complete", "mutant": result.mutant_name,
                      "exit_code": result.exit_code, "elapsed_seconds": time.monotonic() - started})
            count += 1

        while queued:
            candidate = next((row for row in queued if admission.can_submit(row)), None)
            if candidate is None or not runner.has_capacity():
                drain()
                continue
            runner.submit(candidate["mutant"], candidate["tests"], candidate["cpu_time_limit_seconds"],
                          candidate["estimated_test_seconds"])
            admission.submit(candidate)
            on_event({"kind": "submit", "mutant": candidate["mutant"],
                      "elapsed_seconds": time.monotonic() - started})
            queued.remove(candidate)
        runner.signal_work_complete()
        while admission.pending:
            drain()
    except BaseException:
        runner.stop_all_workers()
        raise
    finally:
        runner.shutdown()
    return count


def verify_schedule(schedule, stats, listing, config, resource_policy=None):
    """Reconstruct selection and limits without trusting a scheduler label."""
    resource_policy = policy() if resource_policy is None else resource_policy
    names = [row["id"] for row in listing["mutants"]]
    expected = make_rows([(None, name, None) for name in names],
                         stats["tests_by_mangled_function_name"],
                         stats["duration_by_test"], config, resource_policy)
    if (schedule.get("kind") != "v03_complete_resource_schedule_v1"
            or schedule.get("policy_sha256") != sha256(POLICY_PATH)
            or schedule.get("stats_sha256") != hashlib.sha256(
                json.dumps(stats, sort_keys=True).encode()).hexdigest()
            or schedule.get("rows") != expected):
        raise ValueError("V03 resource schedule differs from frozen population or selected tests")
    return expected


def verify_trace(trace, rows, raw_codes, resource_policy=None):
    """Replay capacity and ensure each runnable mutant retained one raw outcome."""
    admission = Admission(resource_policy)
    runnable = {row["mutant"]: row for row in rows if row["tests"]}
    started, finished = set(), set()
    for event in trace:
        mutant = event["mutant"]
        if event["kind"] == "submit":
            if mutant not in runnable or mutant in started:
                raise ValueError("Missing or repeated V03 scheduled job")
            queued = sorted((row for name, row in runnable.items() if name not in started),
                            key=lambda row: (-row["estimated_test_seconds"], row["mutant"]))
            first = next((row for row in queued if admission.can_submit(row)), None)
            if first is None or first["mutant"] != mutant:
                raise ValueError("V03 admission differs from frozen first-eligible priority")
            admission.submit(runnable[mutant]); started.add(mutant)
        elif event["kind"] == "complete":
            if mutant not in started or mutant in finished or event.get("exit_code") != raw_codes.get(mutant):
                raise ValueError("V03 raw completion differs from schedule trace")
            admission.complete(mutant); finished.add(mutant)
        else:
            raise ValueError("Unknown V03 schedule event")
    if started != finished or finished != set(runnable):
        raise ValueError("V03 scheduled population was not fully drained")
