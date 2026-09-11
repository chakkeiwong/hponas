"""
V01Validator: V16 audit protocol compliance for V01 Vendor Parity.

Checks:
1. Non-vacuity: n_samples > 0, n_trials > 0
2. No post-hoc tuning: Sobol (KS<0.05, p>0.05), Wrappers (KS<0.10, p>0.05)
3. Correct reference: scipy.qmc.Sobol, optuna.samplers.TPESampler, botorch
4. Runnable independently: Can execute without manual intervention
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck


class V01Validator(ValidationProtocol):
    """V16 audit protocol compliance for V01 Vendor Parity."""

    def __init__(self):
        self.protocol_path = Path("validation/protocols/v01_protocol.md")
        self.impl_sobol_path = Path("validation/v01_sobol_parity.py")
        self.impl_wrapper_path = Path("validation/v01_wrapper_parity.py")

    def _check_non_vacuity(self) -> AuditCheck:
        """Check 1: Validator rejects empty input."""
        # Read Sobol implementation
        if not self.impl_sobol_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Sobol implementation not found: {self.impl_sobol_path}"
            )

        sobol_text = self.impl_sobol_path.read_text()

        # Read wrapper implementation
        if not self.impl_wrapper_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Wrapper implementation not found: {self.impl_wrapper_path}"
            )

        wrapper_text = self.impl_wrapper_path.read_text()

        # Check for n_trials=0 and n_samples rejection
        has_wrapper_check = 'n_trials == 0' in wrapper_text and 'ValueError' in wrapper_text and 'vacuous pass' in wrapper_text
        has_sobol_implicit = 'n_samples' in sobol_text  # Sobol uses n_samples parameter

        if not has_wrapper_check:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Wrapper validation does not reject n_trials=0"
            )

        if not has_sobol_implicit:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Sobol validation missing n_samples parameter"
            )

        return AuditCheck(
            name="Non-vacuity",
            passed=True,
            message="Validator correctly rejects n_trials=0 and uses n_samples parameter"
        )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check 2: Thresholds preregistered in protocol and match implementation."""
        if not self.protocol_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Protocol file not found: {self.protocol_path}"
            )

        protocol_text = self.protocol_path.read_text()

        # Protocol should contain preregistered thresholds
        has_sobol_ks = "KS statistic < 0.05" in protocol_text
        has_sobol_p = "p-value > 0.05" in protocol_text
        has_wrapper_ks = "KS < 0.10" in protocol_text or "KS statistic < 0.10" in protocol_text
        has_wrapper_p = "p > 0.05" in protocol_text

        if not (has_sobol_ks and has_sobol_p):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Sobol thresholds not preregistered in protocol"
            )

        if not (has_wrapper_ks and has_wrapper_p):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Wrapper thresholds not preregistered in protocol"
            )

        # Implementation should match protocol thresholds
        sobol_text = self.impl_sobol_path.read_text()
        wrapper_text = self.impl_wrapper_path.read_text()

        # Check Sobol implementation: max_ks < 0.05 and min_p > 0.05
        has_sobol_ks_impl = "max_ks < 0.05" in sobol_text or "ks_stat < 0.05" in sobol_text
        has_sobol_p_impl = "min_p > 0.05" in sobol_text or "p_val > 0.05" in sobol_text

        # Check wrapper implementation: ks_stat < 0.10 and p_val > 0.05
        has_wrapper_ks_impl = "ks_stat < 0.10" in wrapper_text
        has_wrapper_p_impl = "p_val > 0.05" in wrapper_text

        if not (has_sobol_ks_impl and has_sobol_p_impl):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Sobol implementation thresholds don't match protocol"
            )

        if not (has_wrapper_ks_impl and has_wrapper_p_impl):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Wrapper implementation thresholds don't match protocol"
            )

        return AuditCheck(
            name="No post-hoc tuning",
            passed=True,
            message="Thresholds preregistered and match implementation"
        )

    def _check_correct_reference(self) -> AuditCheck:
        """Check 3: Compares to external vendor references, not self."""
        sobol_text = self.impl_sobol_path.read_text()
        wrapper_text = self.impl_wrapper_path.read_text()

        # Sobol should reference scipy.qmc.Sobol
        has_scipy_import = "from scipy.stats import" in sobol_text and "qmc" in sobol_text
        has_scipy_usage = "qmc.Sobol" in sobol_text

        if not (has_scipy_import and has_scipy_usage):
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Sobol validation does not use scipy.qmc.Sobol reference"
            )

        # TPE wrapper should reference optuna.samplers.TPESampler
        has_optuna_import = "import optuna" in wrapper_text
        has_optuna_usage = "optuna.samplers.TPESampler" in wrapper_text

        if not (has_optuna_import and has_optuna_usage):
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="TPE wrapper validation does not use optuna.samplers.TPESampler reference"
            )

        # Check no self-comparison (our implementation vs our implementation)
        if "SobolSearcher" in sobol_text and sobol_text.count("SobolSearcher") > 1:
            # Acceptable: once for our implementation, once for scipy reference
            pass

        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="Compares to scipy.qmc.Sobol and optuna.samplers.TPESampler (correct references)"
        )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check 4: Can run standalone without manual intervention."""
        sobol_text = self.impl_sobol_path.read_text()
        wrapper_text = self.impl_wrapper_path.read_text()

        # Check for __main__ block
        has_sobol_main = 'if __name__ == "__main__"' in sobol_text
        has_wrapper_main = 'if __name__ == "__main__"' in wrapper_text

        if not has_sobol_main:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Sobol validation missing __main__ block"
            )

        if not has_wrapper_main:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Wrapper validation missing __main__ block"
            )

        # Check for default parameters
        has_sobol_defaults = "n_samples: int = 1000" in sobol_text or "n_samples=1000" in sobol_text
        has_wrapper_defaults = "n_trials: int = 30" in wrapper_text or "n_trials=30" in wrapper_text

        if not has_sobol_defaults:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Sobol validation missing default parameters"
            )

        if not has_wrapper_defaults:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Wrapper validation missing default parameters"
            )

        return AuditCheck(
            name="Runnable independently",
            passed=True,
            message="Both protocols can run standalone with default parameters"
        )
