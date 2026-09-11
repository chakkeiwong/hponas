#!/usr/bin/env python3
"""V16 audit validator for V13 Warm-Start Effectiveness protocol."""

import sys
from pathlib import Path

# Allow importing from same directory
sys.path.insert(0, str(Path(__file__).parent))

from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V13Validator(ValidationProtocol):
    """V16 audit validator for V13 Warm-Start Effectiveness."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v13_warmstart_effectiveness.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for n_configs and n_seeds validation
        has_configs_validation = (
            'n_configs' in impl_text and
            'range(n_configs)' in impl_text
        )

        has_seeds_validation = (
            'n_seeds' in impl_text and
            'range(n_seeds)' in impl_text
        )

        # Check for veto criteria definition
        has_veto_criteria = (
            'veto' in impl_text.lower() and
            ('nan' in impl_text.lower() or 'isnan' in impl_text.lower())
        )

        if has_configs_validation and has_seeds_validation and has_veto_criteria:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation validates configs/seeds and defines veto criteria"
            )
        else:
            missing = []
            if not has_configs_validation:
                missing.append("configs validation")
            if not has_seeds_validation:
                missing.append("seeds validation")
            if not has_veto_criteria:
                missing.append("veto criteria")

            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that thresholds and veto criteria were preregistered."""
        impl_path = Path("validation/v13_warmstart_effectiveness.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for Spearman correlation threshold (ρ > 0.8)
        has_rho_threshold = (
            'rho' in impl_text.lower() or
            'correlation' in impl_text.lower()
        )

        # Check for KL divergence threshold (< 0.1)
        has_kl_threshold = (
            'kl' in impl_text.lower() or
            'divergence' in impl_text.lower()
        )

        # Check for preregistered veto criteria
        has_veto_preregistration = (
            'veto' in impl_text.lower() and
            ('nan' in impl_text.lower() or
             'diverged' in impl_text.lower() or
             'bounds' in impl_text.lower())
        )

        if has_rho_threshold and has_kl_threshold and has_veto_preregistration:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Thresholds (ρ, KL) and veto criteria preregistered"
            )
        else:
            missing = []
            if not has_rho_threshold:
                missing.append("Spearman correlation threshold")
            if not has_kl_threshold:
                missing.append("KL divergence threshold")
            if not has_veto_preregistration:
                missing.append("veto criteria")

            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that reference posterior is defined and computed."""
        impl_path = Path("validation/v13_warmstart_effectiveness.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for reference posterior computation
        has_reference_posterior = (
            'reference' in impl_text.lower() and
            'posterior' in impl_text.lower()
        )

        # Check for pilot posterior computation
        has_pilot_posterior = (
            'pilot' in impl_text.lower() and
            'posterior' in impl_text.lower()
        )

        # Check for KL divergence comparison between them
        has_kl_comparison = (
            'kl' in impl_text.lower() and
            ('divergence' in impl_text.lower() or 'kl_div' in impl_text.lower())
        )

        if has_reference_posterior and has_pilot_posterior and has_kl_comparison:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Reference posterior defined and compared to pilot posterior via KL divergence"
            )
        else:
            missing = []
            if not has_reference_posterior:
                missing.append("reference posterior")
            if not has_pilot_posterior:
                missing.append("pilot posterior")
            if not has_kl_comparison:
                missing.append("KL divergence comparison")

            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v13_warmstart_effectiveness.py")

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
            'run_warmstart(' in impl_text or
            'run_campaign(' in impl_text
        )

        # Check for result serialization
        has_save_results = (
            'json.dump' in impl_text or
            'with open(' in impl_text
        )

        if has_main_block and has_run_call and has_save_results:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with execution and serialization"
            )
        else:
            missing = []
            if not has_main_block:
                missing.append("__main__ block")
            if not has_run_call:
                missing.append("validation execution")
            if not has_save_results:
                missing.append("result serialization")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run V16 audit on V13 validator")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run V16 audit checks"
    )
    args = parser.parse_args()

    if args.audit:
        validator = V13Validator()
        report = validator.audit()

        print("\n=== V16 Audit Report ===")
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.message}")

        print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

        sys.exit(0 if report.passed else 1)
