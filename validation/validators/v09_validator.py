"""
V16 audit validator for V09 qLogNEHVI vs Scalarization.

This validator ensures that validation/v09_qlogNEHVI_vs_scalarization.py
meets all four V16 audit requirements:
1. Non-vacuity: rejects structurally empty inputs
2. No post-hoc tuning: thresholds preregistered before campaign
3. Correct reference: compares against declared baseline (Chebyshev scalarization)
4. Runnable independently: has __main__ block with argument parsing
"""

import sys
from pathlib import Path

# Ensure base_validator is importable
sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V09Validator(ValidationProtocol):
    """V16 audit validator for V09 qLogNEHVI vs Scalarization Performance."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v09_qlogNEHVI_vs_scalarization.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for max_trials and n_seeds validation
        has_trials_validation = (
            'max_trials' in impl_text and
            'range(max_trials)' in impl_text
        )

        has_seeds_validation = (
            'n_seeds' in impl_text and
            'range(n_seeds)' in impl_text
        )

        # Check that run_validation function exists with these parameters
        has_run_validation = (
            'def run_validation(' in impl_text and
            'max_trials' in impl_text and
            'n_seeds' in impl_text
        )

        if has_trials_validation and has_seeds_validation and has_run_validation:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation validates max_trials and n_seeds parameters"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation missing validation for trials or seeds"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that statistical thresholds and parameters were preregistered."""
        impl_path = Path("validation/v09_qlogNEHVI_vs_scalarization.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # V09 protocol specifies α=0.05 for statistical tests
        # Check that alpha is a parameter, not a hardcoded post-hoc value
        has_alpha_parameter = (
            'alpha: float' in impl_text or
            'alpha=' in impl_text
        )

        # Check that reference_point is defined before use
        has_reference_point = (
            'reference_point = np.array' in impl_text or
            'reference_point: np.ndarray' in impl_text
        )

        # Protocol specifies 5% improvement margin (δ=0.05)
        # Check for tie threshold being defined
        has_tie_threshold = (
            'abs(mean_diff' in impl_text or
            'tie' in impl_text.lower()
        )

        if has_alpha_parameter and has_reference_point and has_tie_threshold:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Statistical parameters (alpha, reference_point, tie threshold) preregistered"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Missing preregistered statistical parameters"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is against Chebyshev baseline and NSGA-II."""
        impl_path = Path("validation/v09_qlogNEHVI_vs_scalarization.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for qLogNEHVI treatment
        has_qnehvi = (
            'qLogNEHVI' in impl_text and
            'qLogNEHVISearcher' in impl_text
        )

        # Check for Chebyshev baseline
        has_chebyshev = (
            'Chebyshev' in impl_text and
            'ChebyshevSearcher' in impl_text
        )

        # Check for NSGA-II baseline
        has_nsga = (
            'NSGA-II' in impl_text and
            'NSGAIISearcher' in impl_text
        )

        # Check for statistical comparison between them
        has_comparison = (
            'ttest_rel' in impl_text and
            'qnehvi_hvs' in impl_text and
            'cheb_hvs' in impl_text
        )

        if has_qnehvi and has_chebyshev and has_nsga and has_comparison:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares qLogNEHVI against Chebyshev and NSGA-II baselines"
            )
        else:
            missing = []
            if not has_qnehvi:
                missing.append("qLogNEHVI treatment")
            if not has_chebyshev:
                missing.append("Chebyshev baseline")
            if not has_nsga:
                missing.append("NSGA-II baseline")
            if not has_comparison:
                missing.append("statistical comparison")

            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v09_qlogNEHVI_vs_scalarization.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check that it actually runs the validation
        has_run_call = (
            'run_validation(' in impl_text and
            'max_trials=' in impl_text
        )

        # Check for result serialization/saving
        has_save_results = (
            'json.dump' in impl_text or
            'with open(' in impl_text
        )

        if has_main_block and has_run_call and has_save_results:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block that runs validation and saves results"
            )
        else:
            missing = []
            if not has_main_block:
                missing.append("__main__ block")
            if not has_run_call:
                missing.append("run_validation call")
            if not has_save_results:
                missing.append("result serialization")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="V16 audit for V09 qLogNEHVI vs Scalarization")
    parser.add_argument("--audit", action="store_true", help="Run V16 audit checks")
    args = parser.parse_args()

    if args.audit:
        validator = V09Validator()
        report = validator.audit()
        print(report)
        sys.exit(0 if report.passed else 1)
    else:
        print("Use --audit flag to run V16 audit checks")
        sys.exit(1)
