#!/usr/bin/env python3
"""
V16: Validator audit - ensure validators detect the failure modes they exist to catch.

Three audit criteria:
1. Non-vacuity: validators must fail on structurally empty input (zero trials, zero events, zero mutants)
2. No-tuning: performance thresholds must be recorded before data, not tuned afterward
3. Reference-correctness: parity validators must compare against declared reference, not self

Exit codes:
    0 - all validators pass audit
    1 - one or more validators fail audit
"""

import sys
from pathlib import Path


def audit_v01_parity():
    """V01: Wrapped searcher parity against vendor references."""
    print("Auditing V01 (parity)...")

    # Non-vacuity: check that validator fails on empty trials
    issues = []

    # Reference-correctness: must compare against vendor (Optuna TPE, BoTorch GP), not scipy
    validator_path = Path('validation/v01_wrapper_parity.py')
    if not validator_path.exists():
        issues.append("V01 validator not implemented")
        return issues

    content = validator_path.read_text()

    # Check for vendor references
    has_optuna = 'optuna' in content.lower()
    has_botorch = 'botorch' in content.lower()

    if not (has_optuna or has_botorch):
        issues.append("V01 must compare against vendor references (Optuna/BoTorch), not self")

    # Check for empty-input handling
    if 'n_trials == 0' not in content and 'if not trials' not in content:
        issues.append("V01 lacks empty-input check")

    return issues


def audit_v04_floor():
    """V04: Searcher complexity floor."""
    print("Auditing V04 (floor)...")

    issues = []
    validator_path = Path('validation/v04_performance_check.py')

    if not validator_path.exists():
        issues.append("V04 validator not implemented")
        return issues

    content = validator_path.read_text()

    # No-tuning: threshold must be pre-recorded, not computed from results
    if 'threshold' not in content:
        issues.append("V04 lacks pre-recorded threshold")

    # Check that threshold isn't computed from data
    if 'np.percentile' in content or 'np.median' in content or 'np.mean' in content:
        issues.append("V04 threshold appears to be computed from data (post-hoc tuning)")

    # Non-vacuity: must fail on empty trials
    if 'len(trials) == 0' not in content and 'if not trials' not in content:
        issues.append("V04 lacks empty-input check")

    return issues


def audit_v05_transform():
    """V05: Transform matters."""
    print("Auditing V05 (transform)...")

    issues = []
    validator_path = Path('validation/v05_log_warping.py')

    if not validator_path.exists():
        issues.append("V05 validator not implemented")
        return issues

    content = validator_path.read_text()

    # No-tuning: threshold pre-recorded
    if 'threshold' not in content:
        issues.append("V05 lacks pre-recorded threshold")

    # Non-vacuity
    if 'len(trials) == 0' not in content and 'if not trials' not in content:
        issues.append("V05 lacks empty-input check")

    return issues


def audit_v14_reproduction():
    """V14: End-to-end reproduction."""
    print("Auditing V14 (reproduction)...")

    issues = []
    validator_path = Path('validation/v14_day_one_walk.py')

    if not validator_path.exists():
        issues.append("V14 validator not implemented")
        return issues

    content = validator_path.read_text()

    # Non-vacuity: must fail when zero trials ran
    if 'SELECT COUNT' not in content and 'len(trials)' not in content:
        issues.append("V14 lacks trial-count check (cannot detect zero-trial vacuous pass)")

    # Check for ImportError swallowing that causes vacuous passes
    if 'except ImportError' in content and 'pass' in content:
        issues.append("V14 swallows ImportError, allowing vacuous skips")

    return issues


def main():
    print("V16 Validator Audit\n")
    print("=" * 60)

    all_issues = []

    # Audit each validator
    audits = [
        ('V01', audit_v01_parity),
        ('V04', audit_v04_floor),
        ('V05', audit_v05_transform),
        ('V14', audit_v14_reproduction),
    ]

    for vid, audit_fn in audits:
        issues = audit_fn()
        if issues:
            all_issues.extend([(vid, issue) for issue in issues])
            print(f"  ❌ {vid}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"     - {issue}")
        else:
            print(f"  ✅ {vid}: PASS")
        print()

    print("=" * 60)

    if all_issues:
        print(f"\n❌ V16 FAILED: {len(all_issues)} audit issue(s) found\n")
        for vid, issue in all_issues:
            print(f"  {vid}: {issue}")
        sys.exit(1)
    else:
        print("\n✅ V16 PASSED: All validators pass audit\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
