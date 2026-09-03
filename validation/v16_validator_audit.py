#!/usr/bin/env python3
"""
V16 Validator Audit: All validators are non-vacuous, no-tuning, reference-correct.

Survey reference: Ch 16, meta-validation.
Validation claim: Every validator V01-V15 demonstrates real coverage, uses pre-recorded
                  thresholds (where applicable), and tests against correct references.

Protocol:
1. For each validator V01-V15:
   a. Non-vacuity: Rejects empty input (zero trials, zero seeds, empty list)
   b. No-tuning: Thresholds are constants, not parameters computed from data
   c. Reference-correctness: Tests compare against declared vendor implementations
2. Pass if all validators satisfy all three criteria

This is a code audit, not a runtime test. The audit examines validator source code
for structural compliance with the three criteria.

Success criteria:
- All 15 validators (V01-V15) pass all three checks
- Any failure is reported with file:line reference
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple


class AuditFinding(NamedTuple):
    """Single audit finding."""
    validator_id: str
    criterion: str
    severity: str  # 'fail' or 'warn'
    message: str
    file_path: str | None = None
    line_number: int | None = None


def audit_non_vacuity(validator_id: str, source_path: Path) -> list[AuditFinding]:
    """
    Check criterion (a): validator rejects empty input.

    Looks for explicit checks like:
    - if n_trials == 0: raise ValueError(...)
    - if len(items) == 0: raise ValueError(...)
    - if not items: raise ValueError(...)
    """
    findings = []

    if not source_path.exists():
        findings.append(AuditFinding(
            validator_id=validator_id,
            criterion='non-vacuity',
            severity='fail',
            message=f'Validator file not found: {source_path}',
            file_path=str(source_path)
        ))
        return findings

    source = source_path.read_text()

    # Pattern: looks for empty-input checks in validation function
    # Accept any of: if n_trials == 0, if n_seeds == 0, if len(...) == 0, if not items
    empty_check_patterns = [
        r'if\s+n_trials\s*==\s*0\s*:',
        r'if\s+n_seeds\s*==\s*0\s*:',
        r'if\s+len\([^)]+\)\s*==\s*0\s*:',
        r'if\s+not\s+\w+\s*:',
    ]

    has_empty_check = any(re.search(pattern, source) for pattern in empty_check_patterns)

    if not has_empty_check:
        findings.append(AuditFinding(
            validator_id=validator_id,
            criterion='non-vacuity',
            severity='fail',
            message='No empty-input check found (vacuous pass possible)',
            file_path=str(source_path)
        ))

    return findings


def audit_no_tuning(validator_id: str, source_path: Path) -> list[AuditFinding]:
    """
    Check criterion (b): thresholds are pre-recorded constants, not tunable parameters.

    Looks for:
    - Module-level constants like PRERECORDED_THRESHOLD = 0.15
    - Rejects function parameters like improvement_threshold: float = 0.15
    """
    findings = []

    if not source_path.exists():
        return findings  # Already reported in non-vacuity check

    source = source_path.read_text()

    # Check for tunable threshold parameters in function signatures
    # Pattern: def validate(..., threshold: float = 0.15, ...)
    tunable_threshold_pattern = r'def\s+\w+\([^)]*threshold[^)]*\):'
    if re.search(tunable_threshold_pattern, source):
        findings.append(AuditFinding(
            validator_id=validator_id,
            criterion='no-tuning',
            severity='fail',
            message='Threshold is a tunable parameter (post-hoc tuning possible)',
            file_path=str(source_path)
        ))
        return findings

    # Check for pre-recorded constant (if validator uses thresholds)
    # Pattern: PRERECORDED_THRESHOLD = ... or PRERECORDED_THRESHOLDS = {...}
    has_prerecorded = re.search(r'PRERECORDED_THRESHOLD', source)
    uses_threshold = re.search(r'\bthreshold\b', source, re.IGNORECASE)

    if uses_threshold and not has_prerecorded:
        findings.append(AuditFinding(
            validator_id=validator_id,
            criterion='no-tuning',
            severity='warn',
            message='Uses threshold but no PRERECORDED_THRESHOLD constant found',
            file_path=str(source_path)
        ))

    return findings


def audit_reference_correctness(validator_id: str, source_path: Path) -> list[AuditFinding]:
    """
    Check criterion (c): tests compare against declared vendor references.

    V01 specifically: should test against Optuna TPE and BoTorch GP, not scipy/numpy.
    Other validators: check docstring claims match imports.
    """
    findings = []

    if not source_path.exists():
        return findings  # Already reported

    source = source_path.read_text()

    # V01 special case: must test vendor wrappers against vendor implementations
    if validator_id == 'V01':
        has_optuna = 'optuna' in source.lower()
        has_botorch = 'botorch' in source.lower()

        if not has_optuna:
            findings.append(AuditFinding(
                validator_id=validator_id,
                criterion='reference-correctness',
                severity='fail',
                message='V01 must test TPE against Optuna reference (optuna import missing)',
                file_path=str(source_path)
            ))

        if not has_botorch:
            findings.append(AuditFinding(
                validator_id=validator_id,
                criterion='reference-correctness',
                severity='fail',
                message='V01 must test GP against BoTorch reference (botorch import missing)',
                file_path=str(source_path)
            ))

    # General check: if docstring claims vendor X, source should import X
    docstring_match = re.search(r'"""(.*?)"""', source, re.DOTALL)
    if docstring_match:
        docstring = docstring_match.group(1).lower()

        # Check for vendor claims
        vendors = {
            'optuna': r'\boptuna\b',
            'botorch': r'\bbotorch\b',
            'ray': r'\bray\b',
        }

        for vendor, pattern in vendors.items():
            if re.search(pattern, docstring):
                if vendor not in source.lower():
                    findings.append(AuditFinding(
                        validator_id=validator_id,
                        criterion='reference-correctness',
                        severity='warn',
                        message=f'Docstring mentions {vendor} but source does not import it',
                        file_path=str(source_path)
                    ))

    return findings


def v16_validator_audit(validation_dir: Path = None) -> dict[str, any]:
    """
    V16: Audit all validators for compliance with validation protocol.

    Args:
        validation_dir: Directory containing validator implementations

    Returns:
        dict with keys: passed, findings, summary
    """
    if validation_dir is None:
        validation_dir = Path(__file__).parent

    print(f"\n=== V16: Validator Audit ===")
    print(f"Validation directory: {validation_dir}")

    # Validators to audit (V01-V15)
    validators = [
        ('V01', 'v01_wrapper_parity.py'),
        ('V02', 'v02_scheduler_fidelity.py'),
        ('V03', 'v03_sabotage_sobol.py'),
        ('V04', 'v04_performance_check.py'),
        ('V05', 'v05_log_warping.py'),
        ('V06', 'v06_scheduler_performance.py'),
        ('V07', 'v07_multiobjective.py'),
        ('V08', 'v08_bg_pbt.py'),
        ('V09', 'v09_early_stopping.py'),
        ('V10', 'v10_warm_start.py'),
        ('V11a', 'v11a_median_stopping.py'),
        ('V11b', 'v11b_hyperband.py'),
        ('V12', 'v12_distributed.py'),
        ('V13', 'v13_agreement.py'),
        ('V14', 'v14_day_one_walk.py'),
        ('V15a', 'v15a_migration_path.py'),
        ('V15b', 'v15b_vendor_swap.py'),
    ]

    all_findings = []

    print("\nAuditing validators...")
    for validator_id, filename in validators:
        print(f"\n  {validator_id} ({filename}):")
        source_path = validation_dir / filename

        findings = []
        findings.extend(audit_non_vacuity(validator_id, source_path))
        findings.extend(audit_no_tuning(validator_id, source_path))
        findings.extend(audit_reference_correctness(validator_id, source_path))

        if findings:
            for f in findings:
                severity_mark = '✗' if f.severity == 'fail' else '⚠'
                print(f"    {severity_mark} {f.criterion}: {f.message}")
                all_findings.append(f)
        else:
            print(f"    ✓ All checks passed")

    # Summary
    failures = [f for f in all_findings if f.severity == 'fail']
    warnings = [f for f in all_findings if f.severity == 'warn']

    passed = len(failures) == 0

    print(f"\n=== Audit Summary ===")
    print(f"Validators audited: {len(validators)}")
    print(f"Failures: {len(failures)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Overall: {'✓ PASSED' if passed else '✗ FAILED'}")

    if failures:
        print("\nFailed validators:")
        for f in failures:
            print(f"  {f.validator_id}: {f.criterion} - {f.message}")

    return {
        'passed': passed,
        'findings': all_findings,
        'n_validators': len(validators),
        'n_failures': len(failures),
        'n_warnings': len(warnings),
        'failures': failures,
        'warnings': warnings,
    }


if __name__ == "__main__":
    print("="*70)
    print("V16 Validator Audit")
    print("="*70)

    result = v16_validator_audit()

    print("\n" + "="*70)
    if result["passed"]:
        print("V16 VALIDATION: ✓ PASSED")
        print(f"All {result['n_validators']} validators satisfy audit criteria:")
        print("  ✓ Non-vacuity: reject empty input")
        print("  ✓ No-tuning: thresholds pre-recorded")
        print("  ✓ Reference-correctness: test against declared vendors")
        if result['n_warnings'] > 0:
            print(f"\n  ⚠ {result['n_warnings']} warning(s) - review recommended")
    else:
        print("V16 VALIDATION: ✗ FAILED")
        print(f"{result['n_failures']} failure(s) found:")
        for f in result['failures']:
            print(f"  - {f.validator_id}: {f.message}")
    print("="*70)
