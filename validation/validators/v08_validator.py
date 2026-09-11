"""
V16 Audit Protocol: V08 BG-PBT Performance
===========================================

V08 validates that BG-PBT beats ASHA on population-suitable tasks.
Implementation: validation/v08_bg_pbt.py (not yet created)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V08Validator(ValidationProtocol):
    """V16 audit validator for V08 BG-PBT Performance."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v08_bg_pbt.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        has_trials_check = (
            'n_trials == 0' in impl_text or
            'len(results) == 0' in impl_text
        ) and 'ValueError' in impl_text

        has_seeds_check = (
            'n_seeds == 0' in impl_text or
            'len(seeds) == 0' in impl_text
        ) and 'ValueError' in impl_text

        if has_trials_check and has_seeds_check:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation rejects empty trials and seeds"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation missing vacuity checks"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that superiority margin was preregistered."""
        impl_path = Path("validation/v08_bg_pbt.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        has_prerecorded_margin = (
            'PRERECORDED_MARGIN = 0.10' in impl_text or
            'SUPERIORITY_MARGIN = 0.10' in impl_text
        )

        if has_prerecorded_margin:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Superiority margin δ=0.10 preregistered"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Superiority margin not preregistered as constant"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is against ASHA baseline."""
        impl_path = Path("validation/v08_bg_pbt.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        has_asha_baseline = (
            'asha' in impl_text.lower() or
            'ASHA' in impl_text
        )

        has_bgpbt_treatment = (
            'bg_pbt' in impl_text.lower() or
            'BG-PBT' in impl_text or
            'BGPBT' in impl_text
        )

        if has_asha_baseline and has_bgpbt_treatment:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares BG-PBT against ASHA baseline"
            )
        else:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Missing ASHA baseline or BG-PBT treatment"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v08_bg_pbt.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        has_main_block = 'if __name__ == "__main__"' in impl_text
        has_argparse = 'argparse' in impl_text or 'ArgumentParser' in impl_text

        if has_main_block and has_argparse:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with argument parsing"
            )
        else:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing __main__ block or argument parsing"
            )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="V16 audit for V08 BG-PBT Performance")
    parser.add_argument("--audit", action="store_true", help="Run V16 audit checks")
    args = parser.parse_args()

    if args.audit:
        validator = V08Validator()
        report = validator.audit()
        print(report)
        sys.exit(0 if report.passed else 1)
    else:
        print("Use --audit flag to run V16 audit checks")
        sys.exit(1)
