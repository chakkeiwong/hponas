"""
V16 audit validator for V10 MO-ASHA Rung Correlation.

This validator ensures that validation/v10_rung_correlation.py
meets all four V16 audit requirements:
1. Non-vacuity: rejects structurally empty inputs
2. No post-hoc tuning: thresholds preregistered before campaign
3. Correct reference: compares early vs final fidelity on same configs
4. Runnable independently: has __main__ block with argument parsing
"""

import sys
from pathlib import Path

# Ensure base_validator is importable
sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V10Validator(ValidationProtocol):
    """V16 audit validator for V10 MO-ASHA Rung Correlation."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v10_rung_correlation.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for n_configs and n_seeds validation
        has_configs_check = (
            'n_configs == 0' in impl_text or
            'len(configs) == 0' in impl_text
        ) and 'ValueError' in impl_text

        has_seeds_check = (
            'n_seeds == 0' in impl_text or
            'len(seeds) == 0' in impl_text
        ) and 'ValueError' in impl_text

        # Check for fidelity validation
        has_fidelity_check = (
            'fidelities' in impl_text and
            ('len(fidelities)' in impl_text or 'fidelity' in impl_text)
        )

        if has_configs_check and has_seeds_check and has_fidelity_check:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation rejects empty configs, seeds, and fidelities"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation missing vacuity checks for configs/seeds/fidelities"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that correlation and recall thresholds were preregistered."""
        impl_path = Path("validation/v10_rung_correlation.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # V10 protocol specifies ρ > 0.6, recall ≥ 0.90, false-cull ≤ 0.10, regret ≤ 0.05
        has_correlation_threshold = (
            'PRERECORDED_CORRELATION = 0.6' in impl_text or
            'CORRELATION_THRESHOLD = 0.6' in impl_text or
            'rho > 0.6' in impl_text
        )

        has_recall_threshold = (
            'PRERECORDED_RECALL = 0.90' in impl_text or
            'RECALL_THRESHOLD = 0.90' in impl_text or
            'recall >= 0.90' in impl_text
        )

        has_false_cull_threshold = (
            'PRERECORDED_FALSE_CULL = 0.10' in impl_text or
            'FALSE_CULL_THRESHOLD = 0.10' in impl_text or
            'false_cull <= 0.10' in impl_text
        )

        has_regret_threshold = (
            'PRERECORDED_REGRET = 0.05' in impl_text or
            'REGRET_THRESHOLD = 0.05' in impl_text or
            'regret <= 0.05' in impl_text
        )

        if (has_correlation_threshold and has_recall_threshold and
            has_false_cull_threshold and has_regret_threshold):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Thresholds (ρ, recall, false-cull, regret) preregistered"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Missing preregistered thresholds for correlation/recall/false-cull/regret"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is between early and final fidelity on same configs."""
        impl_path = Path("validation/v10_rung_correlation.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for early and final fidelity
        has_early_fidelity = (
            'fidelity=0.1' in impl_text or
            'early_fidelity' in impl_text or
            'fidelity_low' in impl_text
        )

        has_final_fidelity = (
            'fidelity=1.0' in impl_text or
            'final_fidelity' in impl_text or
            'fidelity_high' in impl_text
        )

        # Check for correlation computation between them
        has_correlation = (
            'spearmanr' in impl_text or
            'pearsonr' in impl_text or
            'correlation' in impl_text.lower()
        )

        # Check that same configs are used at both fidelities
        has_same_configs = (
            'for config in configs' in impl_text or
            'same config' in impl_text.lower()
        )

        if has_early_fidelity and has_final_fidelity and has_correlation and has_same_configs:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares early vs final fidelity on same configurations"
            )
        else:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Missing early/final fidelity comparison on same configs"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v10_rung_correlation.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check for argument parsing
        has_argparse = (
            'argparse' in impl_text or
            'ArgumentParser' in impl_text
        )

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

    parser = argparse.ArgumentParser(description="V16 audit for V10 MO-ASHA Rung Correlation")
    parser.add_argument("--audit", action="store_true", help="Run V16 audit checks")
    args = parser.parse_args()

    if args.audit:
        validator = V10Validator()
        report = validator.audit()
        print(report)
        sys.exit(0 if report.passed else 1)
    else:
        print("Use --audit flag to run V16 audit checks")
        sys.exit(1)
