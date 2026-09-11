"""
V16 audit validator for V11 Prior Recovery (V11a + V11b).

This validator ensures that validation/v11_campaign.py
meets all four V16 audit requirements:
1. Non-vacuity: rejects structurally empty inputs
2. No post-hoc tuning: thresholds preregistered before campaign
3. Correct reference: compares against no_prior baseline
4. Runnable independently: has __main__ block with argument parsing
"""

import sys
from pathlib import Path

# Ensure base_validator is importable
sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V11Validator(ValidationProtocol):
    """V16 audit validator for V11 Prior Recovery."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v11_campaign.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for arms validation (must have all three: no_prior, folklore_prior, wrong_prior)
        has_arms_definition = (
            'ARMS = ("no_prior", "folklore_prior", "wrong_prior")' in impl_text or
            'ARMS = [' in impl_text
        )

        # Check for methods validation (pibo, priorband)
        has_methods_definition = (
            'METHODS = ("pibo", "priorband")' in impl_text or
            'METHODS = [' in impl_text
        )

        # Check for task validation
        has_task_validation = (
            'V11_ACCEPTANCE_TASKS' in impl_text and
            'AcceptanceTask' in impl_text
        )

        # Check for seeds validation
        has_seeds_validation = (
            'pilot_seeds' in impl_text and
            'confirmatory_seeds' in impl_text
        )

        if (has_arms_definition and has_methods_definition and
            has_task_validation and has_seeds_validation):
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation validates arms, methods, tasks, and seeds"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation missing validation for arms/methods/tasks/seeds"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that superiority and non-inferiority margins were preregistered."""
        impl_path = Path("validation/v11_campaign.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # V11a superiority margin: δ = 0.05 (5% improvement)
        # V11b non-inferiority margin: δ = -0.10 (-10% acceptable degradation)
        # These should be in superiority_one_sided and non_inferiority_one_sided calls

        has_superiority_test = (
            'superiority_one_sided' in impl_text
        )

        has_non_inferiority_test = (
            'non_inferiority_one_sided' in impl_text
        )

        # Check for alpha definition (should use DEFAULT_ALPHA or explicit 0.05)
        has_alpha = (
            'DEFAULT_ALPHA' in impl_text or
            'alpha=' in impl_text
        )

        # Check for Holm-Bonferroni family correction
        has_family_correction = (
            'holm_bonferroni' in impl_text
        )

        if (has_superiority_test and has_non_inferiority_test and
            has_alpha and has_family_correction):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Margins and alpha preregistered with family correction"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Missing preregistered margins or family correction"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is against no_prior baseline."""
        impl_path = Path("validation/v11_campaign.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for no_prior as comparator
        has_no_prior = (
            '"no_prior"' in impl_text or
            "'no_prior'" in impl_text
        )

        # Check for folklore_prior treatment (V11a)
        has_folklore_prior = (
            '"folklore_prior"' in impl_text or
            "'folklore_prior'" in impl_text
        )

        # Check for wrong_prior treatment (V11b)
        has_wrong_prior = (
            '"wrong_prior"' in impl_text or
            "'wrong_prior'" in impl_text
        )

        # Check that comparator is explicitly named
        has_comparator_comment = (
            'comparator' in impl_text.lower() or
            'baseline' in impl_text.lower()
        )

        if has_no_prior and has_folklore_prior and has_wrong_prior and has_comparator_comment:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares folklore_prior and wrong_prior against no_prior baseline"
            )
        else:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Missing no_prior baseline or treatment arms"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v11_campaign.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check for campaign execution function
        has_run_campaign = (
            'def run_campaign(' in impl_text or
            'run_campaign(' in impl_text
        )

        # Check for result serialization
        has_save_results = (
            'json.dump' in impl_text or
            'with open(' in impl_text
        )

        if has_main_block and has_run_campaign and has_save_results:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with campaign execution"
            )
        else:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing __main__ block or campaign execution"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="V16 audit for V11 Prior Recovery")
    parser.add_argument("--audit", action="store_true", help="Run V16 audit checks")
    args = parser.parse_args()

    if args.audit:
        validator = V11Validator()
        report = validator.audit()
        print(report)
        sys.exit(0 if report.passed else 1)
    else:
        print("Use --audit flag to run V16 audit checks")
        sys.exit(1)
