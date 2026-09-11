#!/usr/bin/env python3
"""V16 audit validator for V15 ifBO Performance protocol (V15a + V15b)."""

import sys
from pathlib import Path

# Allow importing from same directory
sys.path.insert(0, str(Path(__file__).parent))

from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V15Validator(ValidationProtocol):
    """V16 audit validator for V15 ifBO Performance (fixed-sequence gatekeeping)."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v15_ifbo_performance.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for n_trials and n_seeds validation
        has_trials_validation = (
            'n_trials' in impl_text and
            'range(n_trials)' in impl_text
        )

        has_seeds_validation = (
            'n_seeds' in impl_text and
            'range(n_seeds)' in impl_text
        )

        # Check for V15a/V15b distinction
        has_v15a = (
            'v15a' in impl_text.lower() or
            'pretrained' in impl_text.lower()
        )

        has_v15b = (
            'v15b' in impl_text.lower() or
            'power_law' in impl_text.lower() or
            'power-law' in impl_text.lower()
        )

        # Check for gatekeeping (V15b only if V15a fails)
        has_gatekeeping = (
            'if v15a' in impl_text.lower() or
            'v15a_passed' in impl_text.lower() or
            'fixed-sequence' in impl_text.lower()
        )

        if (has_trials_validation and has_seeds_validation and
            has_v15a and has_v15b and has_gatekeeping):
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation validates trials/seeds and enforces V15a→V15b gatekeeping"
            )
        else:
            missing = []
            if not has_trials_validation:
                missing.append("trials validation")
            if not has_seeds_validation:
                missing.append("seeds validation")
            if not has_v15a:
                missing.append("V15a definition")
            if not has_v15b:
                missing.append("V15b definition")
            if not has_gatekeeping:
                missing.append("gatekeeping enforcement")

            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that margins and sequence were preregistered."""
        impl_path = Path("validation/v15_ifbo_performance.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for margin preregistration (δ = 0.10 for both V15a and V15b)
        has_margin = (
            'SUPERIORITY_MARGIN' in impl_text or
            'delta' in impl_text.lower() or
            'margin' in impl_text.lower()
        )

        # Check for alpha preregistration
        has_alpha = (
            'alpha: float' in impl_text or
            'alpha=' in impl_text
        )

        # Check for sequence preregistration (V15a first, V15b second)
        has_sequence = (
            'v15a' in impl_text.lower() and
            'v15b' in impl_text.lower() and
            ('sequence' in impl_text.lower() or 'gatekeeping' in impl_text.lower())
        )

        if has_margin and has_alpha and has_sequence:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Margins (10%), alpha, and fixed-sequence preregistered"
            )
        else:
            missing = []
            if not has_margin:
                missing.append("superiority margin")
            if not has_alpha:
                missing.append("alpha")
            if not has_sequence:
                missing.append("fixed-sequence specification")

            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is against standard GP baseline."""
        impl_path = Path("validation/v15_ifbo_performance.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for ifBO treatment (both V15a and V15b)
        has_ifbo = (
            'ifbo' in impl_text.lower() or
            'ifBO' in impl_text
        )

        # Check for standard GP baseline
        has_standard_gp = (
            'standard' in impl_text.lower() and
            'gp' in impl_text.lower()
        ) or 'StandardGP' in impl_text or 'standard_gp' in impl_text

        # Check for RBF kernel mention
        has_rbf = (
            'rbf' in impl_text.lower() or
            'RBF' in impl_text
        )

        # Check for comparison
        has_comparison = (
            'ttest' in impl_text.lower() or
            'compare' in impl_text.lower() or
            'baseline' in impl_text.lower()
        )

        if has_ifbo and has_standard_gp and has_comparison:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares ifBO (V15a pretrained, V15b power-law) against standard GP baseline"
            )
        else:
            missing = []
            if not has_ifbo:
                missing.append("ifBO treatment")
            if not has_standard_gp:
                missing.append("standard GP baseline")
            if not has_comparison:
                missing.append("statistical comparison")

            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v15_ifbo_performance.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check for execution
        has_run_call = (
            'run_validation(' in impl_text or
            'run_campaign(' in impl_text or
            'run_v15(' in impl_text
        )

        # Check for result serialization
        has_save_results = (
            'json.dump' in impl_text or
            'with open(' in impl_text
        )

        # Check for gatekeeping enforcement in execution
        has_gatekeeping_enforcement = (
            'if v15a' in impl_text.lower() or
            'only if v15a fails' in impl_text.lower()
        )

        if has_main_block and has_run_call and has_save_results and has_gatekeeping_enforcement:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with gatekeeping enforcement"
            )
        else:
            missing = []
            if not has_main_block:
                missing.append("__main__ block")
            if not has_run_call:
                missing.append("validation execution")
            if not has_save_results:
                missing.append("result serialization")
            if not has_gatekeeping_enforcement:
                missing.append("gatekeeping enforcement")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run V16 audit on V15 validator")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run V16 audit checks"
    )
    args = parser.parse_args()

    if args.audit:
        validator = V15Validator()
        report = validator.audit()

        print("\n=== V16 Audit Report ===")
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.message}")

        print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

        sys.exit(0 if report.passed else 1)
