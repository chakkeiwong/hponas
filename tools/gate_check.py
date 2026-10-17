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
            criteria.append(
                Criterion(
                    name=f"Deliverable: {f}", status="met", message=f"File exists"
                )
            )
        else:
            criteria.append(
                Criterion(
                    name=f"Deliverable: {f}",
                    status="blocked",
                    message=f"Missing required file",
                )
            )

    # Deliverable: architecture factory
    if Path("hponas/architecture.py").exists():
        criteria.append(
            Criterion(
                name="Deliverable: architecture.py",
                status="met",
                message="Architecture factory implemented",
            )
        )
    else:
        criteria.append(
            Criterion(
                name="Deliverable: architecture.py",
                status="blocked",
                message="Missing architecture factory",
            )
        )

    # Deliverable: SPIKE_REVIEW.md
    if Path("docs/SPIKE_REVIEW.md").exists():
        criteria.append(
            Criterion(
                name="Deliverable: SPIKE_REVIEW.md",
                status="met",
                message="Interface review signed off",
            )
        )
    else:
        criteria.append(
            Criterion(
                name="Deliverable: SPIKE_REVIEW.md",
                status="blocked",
                message="Missing stakeholder review document",
            )
        )

    # Functional: spike_branin runs and passes determinism
    try:
        result = subprocess.run(
            [sys.executable, "-m", "examples.spike_branin"],
            capture_output=True,
            timeout=120,
            text=True,
        )
        if result.returncode == 0 and "DETERMINISM TEST PASSED" in result.stdout:
            criteria.append(
                Criterion(
                    name="Functional: spike_branin determinism",
                    status="met",
                    message="Branin example runs and passes determinism check",
                )
            )
        else:
            criteria.append(
                Criterion(
                    name="Functional: spike_branin determinism",
                    status="blocked",
                    message=f"Example failed or determinism check missing (rc={result.returncode})",
                )
            )
    except subprocess.TimeoutExpired:
        criteria.append(
            Criterion(
                name="Functional: spike_branin determinism",
                status="blocked",
                message="Example timed out after 120s",
            )
        )
    except Exception as e:
        criteria.append(
            Criterion(
                name="Functional: spike_branin determinism",
                status="blocked",
                message=f"Example crashed: {e}",
            )
        )

    # Functional: crash recovery produces unique configs (STRICT check)
    try:
        # Each invocation retains a unique directory; never delete a user's store.
        import tempfile

        crash_dir = Path(tempfile.mkdtemp(prefix="hponas-r1-recovery-"))

        # Run crash recovery
        result = subprocess.run(
            [sys.executable, "-m", "examples.spike_crash_recovery",
             "--output-dir", str(crash_dir)],
            capture_output=True,
            timeout=180,
            text=True,
        )
        receipts = list(crash_dir.glob("hponas-recovery-*/recovery-receipt.json"))
        if result.returncode == 0 and len(receipts) == 1:
            # Check the actual store for config duplicates (not the example's weak assertion)
            import sqlite3

            receipt = json.loads(receipts[0].read_text())
            db_path = receipts[0].parent / "resumed/study.db"
            if db_path.exists():
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                rows = conn.execute("SELECT config_json FROM trials WHERE status='completed'").fetchall()
                configs = [tuple(sorted(json.loads(cj).items())) for (cj,) in rows]
                conn.close()

                unique = len(set(configs))
                total = len(configs)
                if (unique == total == receipt["trials"] == 16
                        and receipt["committed_preserved"] == 8
                        and receipt["exact_reference_trace"] is True):
                    criteria.append(
                        Criterion(
                            name="Functional: crash recovery uniqueness",
                            status="met",
                            message=f"Crash recovery verified: {unique} unique configs in {total} trials",
                        )
                    )
                else:
                    criteria.append(
                        Criterion(
                            name="Functional: crash recovery uniqueness",
                            status="blocked",
                            message=f"Recovery count, uniqueness or trace mismatch: {unique} unique in {total} trials",
                        )
                    )
            else:
                criteria.append(
                    Criterion(
                        name="Functional: crash recovery uniqueness",
                        status="blocked",
                        message="Crash recovery store not found for verification",
                    )
                )
        else:
            criteria.append(
                Criterion(
                    name="Functional: crash recovery uniqueness",
                    status="blocked",
                    message=f"Crash recovery example failed (rc={result.returncode})",
                )
            )
    except Exception as e:
        criteria.append(
            Criterion(
                name="Functional: crash recovery uniqueness",
                status="blocked",
                message=f"Crash recovery crashed: {e}",
            )
        )

    # Test suite: pytest passes
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q"],
            capture_output=True,
            timeout=300,
            text=True,
        )
        if result.returncode == 0:
            # Extract pass count from output
            if "passed" in result.stdout:
                criteria.append(
                    Criterion(
                        name="Test suite", status="met", message=f"Test suite passed"
                    )
                )
            else:
                criteria.append(
                    Criterion(
                        name="Test suite",
                        status="warning",
                        message="Tests ran but no pass count found",
                    )
                )
        else:
            criteria.append(
                Criterion(
                    name="Test suite",
                    status="blocked",
                    message=f"Test suite failed (rc={result.returncode})",
                )
            )
    except Exception as e:
        criteria.append(
            Criterion(
                name="Test suite", status="blocked", message=f"Test suite error: {e}"
            )
        )

    # Documentation: README survey page count matches reality
    readme = Path("README.md").read_text()
    if "106 pages" in readme:
        criteria.append(
            Criterion(
                name="Documentation sync: README survey pages",
                status="warning",
                message="README claims 106 pages, actual is 114 (stale)",
            )
        )
    elif "114 pages" in readme:
        criteria.append(
            Criterion(
                name="Documentation sync: README survey pages",
                status="met",
                message="README survey page count correct",
            )
        )
    else:
        criteria.append(
            Criterion(
                name="Documentation sync: README survey pages",
                status="warning",
                message="Could not verify survey page count in README",
            )
        )

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
        timestamp=datetime.now().isoformat(),
    )


def check_tier0_gate(artifact_root=None, *, program_root=None) -> GateResult:
    """Require master prerequisites and independently audited Tier 0 campaigns."""
    from tools.program_state import ROOT, tier0_release_blockers
    from validation.evidence import TIER0
    from validation.v16_audit_enforcer import V16Enforcer

    program_root = Path(program_root) if program_root is not None else ROOT
    registered_root = program_root / "validation/artifacts"
    artifact_root = Path(artifact_root) if artifact_root is not None else registered_root
    blockers = tier0_release_blockers(program_root)
    if artifact_root.resolve() != registered_root.resolve():
        blockers.append("Campaign root differs from the master program's registered artifacts")
    criteria = [Criterion(
        name="Master program prerequisites",
        status="blocked" if blockers else "met",
        message="; ".join(blockers) if blockers else "Program, protocol decisions, requirements and release prerequisites are ready for review",
    )]
    for vid in TIER0:
        try:
            pointer = json.loads((artifact_root / vid / "latest.json").read_text())
            run_dir = artifact_root / vid / pointer["run"]
            if run_dir.parent.resolve() != (artifact_root / vid).resolve():
                raise ValueError("Invalid run path")
            protocol = program_root / "validation/protocols" / (
                vid.lower().replace("-", "_") + "_protocol.md"
            )
            audit = V16Enforcer(protocol).audit_execution(run_dir)
            result = json.loads((run_dir / "results.json").read_text())
            met = audit.passed and result.get("verdict") == "PASS"
            message = (
                "Campaign and V16 passed"
                if met
                else "; ".join(
                    [f"Campaign: {result.get('verdict', 'missing')}"]
                    + [c.message for c in audit.checks if not c.passed]
                )
            )
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            met, message = False, f"Missing or invalid campaign evidence: {exc}"
        criteria.append(
            Criterion(name=vid, status="met" if met else "blocked", message=message)
        )
    return GateResult(
        phase="tier0",
        verdict="pass" if all(c.status == "met" for c in criteria) else "blocked",
        criteria=criteria,
        timestamp=datetime.now().isoformat(),
    )


def print_report(result: GateResult, mode: str = "run"):
    """Print human-readable gate report."""
    print(f"\n{'=' * 80}")
    print(f"GATE CHECK: {result.phase.upper()}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Mode: {mode}")
    print(f"{'=' * 80}\n")

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

    print(f"{'=' * 80}")
    print(f"VERDICT: {result.verdict.upper()}")
    print(f"{'=' * 80}\n")

    if result.verdict == "pass":
        if result.phase == "tier0":
            print("✅ Campaigns and master prerequisites pass. REL-01 review and explicit release approval are still required.")
        elif result.phase == "tier1":
            print("Finite opt-in Tier-1 capability criteria pass. Integrated-source release remains separate.")
        else:
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
            if result.phase == "tier0":
                f.write("**Decision:** Campaigns and master prerequisites pass. REL-01 review and explicit release approval are still required.\n")
            elif result.phase == "tier1":
                f.write("**Decision:** Finite opt-in Tier-1 capability criteria pass. Integrated-source release remains separate.\n")
            else:
                f.write("**Decision:** Phase may close. All exit criteria met.\n")
        elif result.verdict == "hold":
            f.write("**Decision:** Review warnings before proceeding.\n")
        elif result.verdict == "blocked":
            f.write(
                "**Decision:** Phase cannot close. Resolve blockers and re-run gate check.\n"
            )

    print(f"\nGate report written to: {report_path}")
    return report_path


def _uncertified_gate(phase):
    return GateResult(
        phase=phase,
        verdict="blocked",
        timestamp=datetime.now().isoformat(),
        criteria=[
            Criterion(
                name="Campaign evidence",
                status="blocked",
                message="Current audited campaign evidence and reconciled protocol identities are required; source inspections cannot certify this tier.",
            )
        ],
    )


def check_tier1_gate():
    from tools.tier1_gate import evaluate
    report=evaluate()
    criteria=[Criterion(row['entry'],'met' if row['passed'] else 'blocked',
                        row.get('reason',str(row.get('verdict','')))) for row in report['criteria']]
    criteria.append(Criterion('Acceptance scope','met',
        'Finite opt-in capability gate only. No automatic defaults or integrated product release.'))
    return GateResult('tier1','pass' if report['passed'] else 'blocked',criteria,datetime.now().isoformat())


def check_tier2_gate():
    return _uncertified_gate("tier2")


def main():
    parser = argparse.ArgumentParser(description="Gate check for phase exit criteria")
    parser.add_argument(
        "--phase",
        required=True,
        choices=["r1", "tier0", "tier1", "tier2"],
        help="Phase to check",
    )
    parser.add_argument(
        "--mode",
        default="run",
        choices=["run", "dry-run"],
        help="run = write report, dry-run = print only",
    )

    args = parser.parse_args()

    # Run appropriate gate check
    if args.phase == "r1":
        result = check_r1_gate()
    elif args.phase == "tier0":
        result = check_tier0_gate()
    elif args.phase == "tier1":
        result = check_tier1_gate()
    elif args.phase == "tier2":
        result = check_tier2_gate()
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
