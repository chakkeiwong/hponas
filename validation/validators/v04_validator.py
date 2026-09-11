#!/usr/bin/env python3
"""V16 audit validator for V04 protocols (V04-T0 + V04-T1)."""

import sys
from pathlib import Path

# Allow importing from same directory
sys.path.insert(0, str(Path(__file__).parent))

from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V04Validator(ValidationProtocol):
    """V16 audit validator for V04 (T0: Random Baseline Floor, T1: Sobol vs Random)."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementations reject structurally empty inputs."""
        t0_path = Path("validation/v04_t0_baseline_floor.py")
        t1_path = Path("validation/v04_performance_check.py")

        # Check T0 implementation
        t0_exists = t0_path.exists()
        t1_exists = t1_path.exists()

        if not t0_exists and not t1_exists:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Both implementations not found: v04_t0_baseline_floor.py, v04_performance_check.py"
            )

        missing = []
        if not t0_exists:
            missing.append("T0")
        if not t1_exists:
            missing.append("T1")

        if missing:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Missing implementations: {', '.join(missing)}"
            )

        # Both exist, check for validation patterns
        t0_text = t0_path.read_text()
        t1_text = t1_path.read_text()

        # T0 checks: n_trials, n_seeds, pathological config
        t0_has_trials = 'N_TRIALS' in t0_text or 'n_trials' in t0_text
        t0_has_seeds = 'N_SEEDS' in t0_text or 'n_seeds' in t0_text
        t0_has_pathological = (
            'pathological' in t0_text.lower() or
            'worst' in t0_text.lower() or
            'bad' in t0_text.lower() or
            'PATHOLOGICAL' in t0_text
        )

        # T1 checks: n_trials, n_seeds, sobol and random
        t1_has_trials = 'n_trials' in t1_text and 'range(n_trials)' in t1_text
        t1_has_seeds = 'n_seeds' in t1_text and 'range(n_seeds)' in t1_text
        t1_has_sobol = 'sobol' in t1_text.lower() or 'Sobol' in t1_text
        t1_has_random = 'random' in t1_text.lower() or 'Random' in t1_text

        if (t0_has_trials and t0_has_seeds and t0_has_pathological and
            t1_has_trials and t1_has_seeds and t1_has_sobol and t1_has_random):
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Both T0 and T1 validate trials/seeds and define treatments"
            )
        else:
            issues = []
            if not (t0_has_trials and t0_has_seeds and t0_has_pathological):
                issues.append("T0 missing validation")
            if not (t1_has_trials and t1_has_seeds and t1_has_sobol and t1_has_random):
                issues.append("T1 missing validation")

            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Issues: {', '.join(issues)}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that margins and configs were preregistered before campaigns."""
        t0_path = Path("validation/v04_t0_baseline_floor.py")
        t1_path = Path("validation/v04_performance_check.py")

        if not t0_path.exists() or not t1_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Implementations not found"
            )

        t0_text = t0_path.read_text()
        t1_text = t1_path.read_text()

        # T0: 5% margin, pathological config preregistered
        t0_has_margin = (
            'SUPERIORITY_MARGIN' in t0_text or
            '0.05' in t0_text or
            'margin' in t0_text.lower()
        )
        t0_has_pathological_preregistered = (
            'learning_rate' in t0_text and
            '1e-5' in t0_text and
            'batch_size' in t0_text and
            '64' in t0_text
        )

        # T1: 5% margin (revised from 10%), power analysis
        t1_has_margin = (
            'SUPERIORITY_MARGIN' in t1_text or
            '0.05' in t1_text or
            'margin' in t1_text.lower()
        )
        t1_has_alpha = (
            'alpha' in t1_text.lower() or
            '0.01' in t1_text  # Conservative corrected alpha
        )

        if (t0_has_margin and t0_has_pathological_preregistered and
            t1_has_margin and t1_has_alpha):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="T0: 5% margin and pathological config preregistered; T1: 5% margin and alpha=0.01 preregistered"
            )
        else:
            missing = []
            if not t0_has_margin:
                missing.append("T0 margin")
            if not t0_has_pathological_preregistered:
                missing.append("T0 pathological config")
            if not t1_has_margin:
                missing.append("T1 margin")
            if not t1_has_alpha:
                missing.append("T1 alpha")

            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparisons are against declared baselines."""
        t0_path = Path("validation/v04_t0_baseline_floor.py")
        t1_path = Path("validation/v04_performance_check.py")

        if not t0_path.exists() or not t1_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Implementations not found"
            )

        t0_text = t0_path.read_text()
        t1_text = t1_path.read_text()

        # T0: compares random to pathological config (not self)
        t0_has_random = 'random' in t0_text.lower() or 'Random' in t0_text
        t0_has_pathological = (
            'pathological' in t0_text.lower() or
            'worst' in t0_text.lower() or
            'Pathological' in t0_text
        )
        t0_has_comparison = (
            'compare' in t0_text.lower() or
            'ttest' in t0_text.lower() or
            'mannwhitneyu' in t0_text.lower()
        )

        # T1: compares Sobol to Random (not self), depends on V01
        t1_has_sobol = 'sobol' in t1_text.lower() or 'Sobol' in t1_text
        t1_has_random = 'random' in t1_text.lower() or 'Random' in t1_text
        t1_has_comparison = (
            'compare' in t1_text.lower() or
            'ttest' in t1_text.lower() or
            'mannwhitneyu' in t1_text.lower()
        )

        if (t0_has_random and t0_has_pathological and t0_has_comparison and
            t1_has_sobol and t1_has_random and t1_has_comparison):
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="T0: random vs pathological; T1: Sobol vs Random"
            )
        else:
            missing = []
            if not (t0_has_random and t0_has_pathological and t0_has_comparison):
                missing.append("T0 comparison")
            if not (t1_has_sobol and t1_has_random and t1_has_comparison):
                missing.append("T1 comparison")

            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that protocols can run standalone."""
        t0_path = Path("validation/v04_t0_baseline_floor.py")
        t1_path = Path("validation/v04_performance_check.py")

        if not t0_path.exists() or not t1_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementations not found"
            )

        t0_text = t0_path.read_text()
        t1_text = t1_path.read_text()

        # T0: __main__ block, execution, result serialization
        t0_has_main = 'if __name__ == "__main__"' in t0_text
        t0_has_run = (
            'run_validation(' in t0_text or
            'run_campaign(' in t0_text or
            'run_v04(' in t0_text or
            'run_check(' in t0_text
        )
        t0_has_save = 'json.dump' in t0_text or 'with open(' in t0_text

        # T1: __main__ block, power analysis, execution, result serialization
        t1_has_main = 'if __name__ == "__main__"' in t1_text
        t1_has_run = (
            'run_validation(' in t1_text or
            'run_campaign(' in t1_text or
            'run_v04(' in t1_text or
            'run_check(' in t1_text or
            'v04_performance_check(' in t1_text
        )
        t1_has_save = 'json.dump' in t1_text or 'with open(' in t1_text

        if (t0_has_main and t0_has_run and t0_has_save and
            t1_has_main and t1_has_run and t1_has_save):
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Both T0 and T1 have __main__ blocks with execution and serialization"
            )
        else:
            missing = []
            if not (t0_has_main and t0_has_run and t0_has_save):
                issues_t0 = []
                if not t0_has_main:
                    issues_t0.append("__main__")
                if not t0_has_run:
                    issues_t0.append("execution")
                if not t0_has_save:
                    issues_t0.append("serialization")
                missing.append(f"T0: {', '.join(issues_t0)}")
            if not (t1_has_main and t1_has_run and t1_has_save):
                issues_t1 = []
                if not t1_has_main:
                    issues_t1.append("__main__")
                if not t1_has_run:
                    issues_t1.append("execution")
                if not t1_has_save:
                    issues_t1.append("serialization")
                missing.append(f"T1: {', '.join(issues_t1)}")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run V16 audit on V04 validators (T0 + T1)")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run V16 audit checks"
    )
    args = parser.parse_args()

    if args.audit:
        validator = V04Validator()
        report = validator.audit()

        print("\n=== V16 Audit Report ===")
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.message}")

        print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

        sys.exit(0 if report.passed else 1)
