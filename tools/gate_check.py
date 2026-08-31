#!/usr/bin/env python3
"""
Gate check: mechanical verification of phase exit criteria.

Usage:
    python3 tools/gate_check.py --phase r1 [--mode dry-run]

Exit codes:
    0 = PASS (all criteria met)
    1 = BLOCKED (missing deliverables or failing criteria)
    2 = HOLD (warnings, may proceed with acknowledged risk)
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Criterion:
    name: str
    status: Literal["met", "blocked", "warning"]
    message: str


@dataclass
class GateResult:
    phase: str
    verdict: Literal["pass", "blocked", "hold"]
    criteria: list[Criterion]
    timestamp: str


def check_r1_gate() -> GateResult:
    """R1 Executable Spike exit criteria."""
    criteria = []

    # Deliverable: spike examples exist
    for f in ["examples/spike_branin.py", "examples/spike_crash_recovery.py"]:
        if Path(f).exists():
            criteria.append(Criterion(
                name=f"Deliverable: {f}",
                status="met",
                message=f"File exists"
            ))
        else:
            criteria.append(Criterion(
                name=f"Deliverable: {f}",
                status="blocked",
                message=f"Missing required file"
            ))

    # Deliverable: architecture factory
    if Path("hponas/architecture.py").exists():
        criteria.append(Criterion(
            name="Deliverable: architecture.py",
            status="met",
            message="Architecture factory implemented"
        ))
    else:
        criteria.append(Criterion(
            name="Deliverable: architecture.py",
            status="blocked",
            message="Missing architecture factory"
        ))

    # Deliverable: SPIKE_REVIEW.md
    if Path("docs/SPIKE_REVIEW.md").exists():
        criteria.append(Criterion(
            name="Deliverable: SPIKE_REVIEW.md",
            status="met",
            message="Interface review signed off"
        ))
    else:
        criteria.append(Criterion(
            name="Deliverable: SPIKE_REVIEW.md",
            status="blocked",
            message="Missing stakeholder review document"
        ))

    # Functional: spike_branin runs and passes determinism
    try:
        result = subprocess.run(
            ["python3", "examples/spike_branin.py"],
            capture_output=True,
            timeout=120,
            text=True
        )
        if result.returncode == 0 and "DETERMINISM TEST PASSED" in result.stdout:
            criteria.append(Criterion(
                name="Functional: spike_branin determinism",
                status="met",
                message="Branin example runs and passes determinism check"
            ))
        else:
            criteria.append(Criterion(
                name="Functional: spike_branin determinism",
                status="blocked",
                message=f"Example failed or determinism check missing (rc={result.returncode})"
            ))
    except subprocess.TimeoutExpired:
        criteria.append(Criterion(
            name="Functional: spike_branin determinism",
            status="blocked",
            message="Example timed out after 120s"
        ))
    except Exception as e:
        criteria.append(Criterion(
            name="Functional: spike_branin determinism",
            status="blocked",
            message=f"Example crashed: {e}"
        ))

    # Functional: crash recovery produces unique configs (STRICT check)
    try:
        # Start from a clean store: the example takes the "restart" path if one exists,
        # so a stale store would make this check report the previous run's state.
        import shutil
        crash_dir = Path("/tmp/hponas_crash")
        if crash_dir.exists():
            shutil.rmtree(crash_dir)

        # Run crash recovery
        result = subprocess.run(
            ["python3", "examples/spike_crash_recovery.py"],
            capture_output=True,
            timeout=180,
            text=True
        )
        if result.returncode == 0 and "CRASH RECOVERY DEMONSTRATION COMPLETE" in result.stdout:
            # Check the actual store for config duplicates (not the example's weak assertion)
            import sqlite3
            db_path = Path("/tmp/hponas_crash/study_crash.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                rows = conn.execute("SELECT config_json FROM trials").fetchall()
                configs = [tuple(sorted(json.loads(cj).items())) for (cj,) in rows]
                conn.close()

                unique = len(set(configs))
                total = len(configs)
                if unique == total:
                    criteria.append(Criterion(
                        name="Functional: crash recovery uniqueness",
                        status="met",
                        message=f"Crash recovery verified: {unique} unique configs in {total} trials"
                    ))
                else:
                    criteria.append(Criterion(
                        name="Functional: crash recovery uniqueness",
                        status="blocked",
                        message=f"DUPLICATE CONFIGS: {unique} unique in {total} trials (Sobol state not restored)"
                    ))
            else:
                criteria.append(Criterion(
                    name="Functional: crash recovery uniqueness",
                    status="blocked",
                    message="Crash recovery store not found for verification"
                ))
        else:
            criteria.append(Criterion(
                name="Functional: crash recovery uniqueness",
                status="blocked",
                message=f"Crash recovery example failed (rc={result.returncode})"
            ))
    except Exception as e:
        criteria.append(Criterion(
            name="Functional: crash recovery uniqueness",
            status="blocked",
            message=f"Crash recovery crashed: {e}"
        ))

    # Test suite: pytest passes
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q"],
            capture_output=True,
            timeout=300,
            text=True
        )
        if result.returncode == 0:
            # Extract pass count from output
            if "passed" in result.stdout:
                criteria.append(Criterion(
                    name="Test suite",
                    status="met",
                    message=f"Test suite passed"
                ))
            else:
                criteria.append(Criterion(
                    name="Test suite",
                    status="warning",
                    message="Tests ran but no pass count found"
                ))
        else:
            criteria.append(Criterion(
                name="Test suite",
                status="blocked",
                message=f"Test suite failed (rc={result.returncode})"
            ))
    except Exception as e:
        criteria.append(Criterion(
            name="Test suite",
            status="blocked",
            message=f"Test suite error: {e}"
        ))

    # Documentation: README survey page count matches reality
    readme = Path("README.md").read_text()
    if "106 pages" in readme:
        criteria.append(Criterion(
            name="Documentation sync: README survey pages",
            status="warning",
            message="README claims 106 pages, actual is 114 (stale)"
        ))
    elif "114 pages" in readme:
        criteria.append(Criterion(
            name="Documentation sync: README survey pages",
            status="met",
            message="README survey page count correct"
        ))
    else:
        criteria.append(Criterion(
            name="Documentation sync: README survey pages",
            status="warning",
            message="Could not verify survey page count in README"
        ))

    # Determine verdict
    blocked = [c for c in criteria if c.status == "blocked"]
    warnings = [c for c in criteria if c.status == "warning"]

    if blocked:
        verdict = "blocked"
    elif warnings:
        verdict = "hold"
    else:
        verdict = "pass"

    return GateResult(
        phase="r1",
        verdict=verdict,
        criteria=criteria,
        timestamp=datetime.now().isoformat()
    )


def check_tier0_gate() -> GateResult:
    """Tier 0 Foundation exit criteria (placeholder)."""
    # TODO: implement after Tier 0 scope finalized
    return GateResult(
        phase="tier0",
        verdict="blocked",
        criteria=[Criterion(
            name="Tier 0 gate",
            status="blocked",
            message="Tier 0 not yet started"
        )],
        timestamp=datetime.now().isoformat()
    )


def print_report(result: GateResult, mode: str = "run"):
    """Print human-readable gate report."""
    print(f"\n{'='*80}")
    print(f"GATE CHECK: {result.phase.upper()}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Mode: {mode}")
    print(f"{'='*80}\n")

    # Group by status
    met = [c for c in result.criteria if c.status == "met"]
    blocked = [c for c in result.criteria if c.status == "blocked"]
    warnings = [c for c in result.criteria if c.status == "warning"]

    if met:
        print(f"✅ MET ({len(met)}):")
        for c in met:
            print(f"   • {c.name}: {c.message}")
        print()

    if warnings:
        print(f"⚠️  WARNINGS ({len(warnings)}):")
        for c in warnings:
            print(f"   • {c.name}: {c.message}")
        print()

    if blocked:
        print(f"❌ BLOCKED ({len(blocked)}):")
        for c in blocked:
            print(f"   • {c.name}: {c.message}")
        print()

    print(f"{'='*80}")
    print(f"VERDICT: {result.verdict.upper()}")
    print(f"{'='*80}\n")

    if result.verdict == "pass":
        print("✅ All exit criteria met. Phase may close.")
    elif result.verdict == "hold":
        print("⚠️  Warnings present. Review before proceeding.")
    elif result.verdict == "blocked":
        print("❌ Blockers present. Must resolve before phase close.")

    if mode == "dry-run":
        print("\n(dry-run mode: no gate report written)")


def write_report(result: GateResult, output_dir: Path):
    """Write gate report to file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = output_dir / f"{result.phase}_gate_{date_str}.md"

    with open(report_path, "w") as f:
        f.write(f"# {result.phase.upper()} Gate Report\n\n")
        f.write(f"**Date:** {result.timestamp}\n")
        f.write(f"**Verdict:** {result.verdict.upper()}\n\n")
        f.write("---\n\n")

        f.write("## Exit Criteria\n\n")
        for c in result.criteria:
            icon = {"met": "✅", "blocked": "❌", "warning": "⚠️"}[c.status]
            f.write(f"### {icon} {c.name}\n\n")
            f.write(f"**Status:** {c.status}\n\n")
            f.write(f"{c.message}\n\n")

        f.write("---\n\n")
        f.write("## Summary\n\n")
        met = len([c for c in result.criteria if c.status == "met"])
        blocked = len([c for c in result.criteria if c.status == "blocked"])
        warnings = len([c for c in result.criteria if c.status == "warning"])
        total = len(result.criteria)

        f.write(f"- **Total criteria:** {total}\n")
        f.write(f"- **Met:** {met}\n")
        f.write(f"- **Warnings:** {warnings}\n")
        f.write(f"- **Blocked:** {blocked}\n\n")

        if result.verdict == "pass":
            f.write("**Decision:** Phase may close. All exit criteria met.\n")
        elif result.verdict == "hold":
            f.write("**Decision:** Review warnings before proceeding.\n")
        elif result.verdict == "blocked":
            f.write("**Decision:** Phase cannot close. Resolve blockers and re-run gate check.\n")

    print(f"\nGate report written to: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Gate check for phase exit criteria")
    parser.add_argument("--phase", required=True, choices=["r1", "tier0", "tier1", "tier2"],
                       help="Phase to check")
    parser.add_argument("--mode", default="run", choices=["run", "dry-run"],
                       help="run = write report, dry-run = print only")

    args = parser.parse_args()

    # Run appropriate gate check
    if args.phase == "r1":
        result = check_r1_gate()
    elif args.phase == "tier0":
        result = check_tier0_gate()
    else:
        print(f"Gate check for {args.phase} not yet implemented")
        sys.exit(1)

    # Print report
    print_report(result, args.mode)

    # Write report if not dry-run
    if args.mode == "run":
        write_report(result, Path("gate_reports"))

    # Exit with appropriate code
    if result.verdict == "pass":
        sys.exit(0)
    elif result.verdict == "hold":
        sys.exit(2)
    else:  # blocked
        sys.exit(1)


if __name__ == "__main__":
    main()
