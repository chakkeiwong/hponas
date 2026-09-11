#!/usr/bin/env python3
"""V03 Mutation Testing Protocol Implementation.

V16 Audit Compliance:
- Non-vacuity: Fails if <100 mutants generated
- No post-hoc tuning: Kill score threshold 0.90 hardcoded (preregistered)
- Correct reference: N/A (deterministic test, not comparative)
- Runnable independently: Standalone main() block

Protocol: validation/protocols/v03_protocol.md
Version: 1.0
Created: 2026-09-09
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MutantResult:
    """Individual mutant result."""
    id: str
    module: str
    line: int
    status: str  # killed, survived, timeout, equivalent
    reason: str = ""


@dataclass
class ModuleScore:
    """Per-module mutation testing score."""
    module: str
    total: int
    killed: int
    survived: int
    timeout: int
    equivalent: int
    kill_score: float
    passed: bool


class V03MutationTesting:
    """Mutation testing validation protocol.

    V16 Audit Compliance:
    - Non-vacuity: Requires ≥100 mutants total
    - No post-hoc tuning: KILL_SCORE_THRESHOLD=0.90 hardcoded
    - Correct reference: N/A (deterministic veto)
    - Runnable independently: Has standalone __main__ block
    """

    # Preregistered thresholds (immutable, no post-hoc tuning)
    KILL_SCORE_THRESHOLD = 0.90
    EQUIVALENT_THRESHOLD = 0.05
    TIMEOUT_THRESHOLD = 0.20
    MIN_MUTANTS = 100  # V16 non-vacuity requirement

    # Preregistered target modules
    IN_SCOPE_MODULES = [
        "hponas/searchers.py",
        "hponas/schedulers.py",
        "hponas/acquisitions.py",
        "hponas/space.py",
        "hponas/executor.py"
    ]

    # Preregistered critical paths (zero survivors required)
    CRITICAL_PATHS = [
        "acquisitions.py:optimize_",
        "searchers.py:GP.posterior",
        "schedulers.py:ASHA.promote",
        "acquisitions.py:qLogNEHVI._compute_hv",
        "executor.py:execute_trial"
    ]

    def __init__(self):
        """Initialize mutation testing validator."""
        self.mutants: List[MutantResult] = []
        self.module_scores: List[ModuleScore] = []
        self.equivalent_mutants: List[Dict[str, Any]] = []
        self.critical_survivors: List[str] = []

    def check_mutmut_available(self) -> bool:
        """Check if mutmut tool is available."""
        try:
            result = subprocess.run(
                ["mutmut", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("mutmut not available")
            return False

    def parse_mutmut_results(self, cache_dir: Path) -> Tuple[int, int, int, int]:
        """Parse mutmut cache results.

        Returns: (total, killed, survived, timeout)
        """
        # BLOCKED: mutmut not installed, cache format unknown
        # This is a stub implementation for V16 compliance
        logger.warning("mutmut cache parsing BLOCKED: tool not installed")
        return (0, 0, 0, 0)

    def calculate_kill_score(self, killed: int, total: int, equivalent: int, timeout: int) -> float:
        """Calculate mutation kill score."""
        denominator = total - equivalent - timeout
        if denominator == 0:
            return 0.0
        return killed / denominator

    def check_critical_paths(self) -> List[str]:
        """Check for survivors in critical paths."""
        survivors = []
        for mutant in self.mutants:
            if mutant.status == "survived":
                for critical_path in self.CRITICAL_PATHS:
                    if critical_path in f"{mutant.module}:{mutant.line}":
                        survivors.append(
                            f"{mutant.module}:{mutant.line} (mutant {mutant.id})"
                        )
        return survivors

    def validate_equivalent_mutants(self, total: int) -> bool:
        """Validate equivalent mutants ≤5% threshold."""
        if total == 0:
            return True
        equivalent_ratio = len(self.equivalent_mutants) / total
        return equivalent_ratio <= self.EQUIVALENT_THRESHOLD

    def run_mutation_testing(self) -> Dict[str, Any]:
        """Run mutation testing and generate results.

        Returns: Results dict with V16 audit metadata.
        """
        logger.info("Starting V03 mutation testing protocol")

        # Check tool availability
        if not self.check_mutmut_available():
            return {
                "validation_id": "v03_mutation_testing",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "protocol_version": "1.0",
                "status": "BLOCKED",
                "reason": "mutmut tool not available",
                "v16_audit": {
                    "non_vacuity": False,
                    "no_posthoc_tuning": True,
                    "correct_reference": None,  # N/A for deterministic veto
                    "runnable_independently": True
                },
                "blocked_on": "mutmut installation (pip install mutmut)"
            }

        # Parse mutmut results (BLOCKED: tool not installed)
        total, killed, survived, timeout = self.parse_mutmut_results(Path(".mutmut-cache"))

        # V16 non-vacuity check
        if total < self.MIN_MUTANTS:
            logger.error(f"V16 non-vacuity FAILED: {total} mutants < {self.MIN_MUTANTS} required")
            return {
                "validation_id": "v03_mutation_testing",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "protocol_version": "1.0",
                "status": "FAILED",
                "reason": f"Non-vacuous test requires ≥{self.MIN_MUTANTS} mutants, got {total}",
                "overall": {
                    "total_mutants": total,
                    "killed": killed,
                    "survived": survived,
                    "timeout": timeout,
                    "equivalent": len(self.equivalent_mutants),
                    "kill_score": 0.0,
                    "passed": False
                },
                "v16_audit": {
                    "non_vacuity": False,
                    "no_posthoc_tuning": True,
                    "correct_reference": None,
                    "runnable_independently": True
                }
            }

        # Calculate overall kill score
        equivalent_count = len(self.equivalent_mutants)
        kill_score = self.calculate_kill_score(killed, total, equivalent_count, timeout)

        # Check critical paths
        self.critical_survivors = self.check_critical_paths()

        # Validate equivalent mutants threshold
        equiv_valid = self.validate_equivalent_mutants(total)

        # Determine pass/fail
        passed = (
            kill_score >= self.KILL_SCORE_THRESHOLD and
            len(self.critical_survivors) == 0 and
            equiv_valid
        )

        return {
            "validation_id": "v03_mutation_testing",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "protocol_version": "1.0",
            "tool": "mutmut",
            "status": "PASS" if passed else "FAIL",
            "overall": {
                "total_mutants": total,
                "killed": killed,
                "survived": survived,
                "timeout": timeout,
                "equivalent": equivalent_count,
                "kill_score": kill_score,
                "passed": passed
            },
            "per_module": [asdict(m) for m in self.module_scores],
            "critical_survivors": self.critical_survivors,
            "equivalent_mutants": self.equivalent_mutants,
            "v16_audit": {
                "non_vacuity": total >= self.MIN_MUTANTS,
                "no_posthoc_tuning": True,
                "correct_reference": None,
                "runnable_independently": True
            }
        }


def main():
    """Run V03 mutation testing protocol."""
    logger.info("=" * 80)
    logger.info("V03 Mutation Testing Protocol")
    logger.info("=" * 80)

    validator = V03MutationTesting()
    results = validator.run_mutation_testing()

    # Write results
    output_path = Path("validation/results/v03_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results written to: {output_path}")

    # Summary
    status = results.get("status", "UNKNOWN")
    logger.info("-" * 80)
    logger.info(f"Status: {status}")

    if "overall" in results:
        overall = results["overall"]
        logger.info(f"Kill Score: {overall['kill_score']:.2f} (threshold: {validator.KILL_SCORE_THRESHOLD})")
        logger.info(f"Mutants: {overall['killed']}/{overall['total_mutants']} killed")
        logger.info(f"Critical Path Survivors: {len(results.get('critical_survivors', []))}")

    if "blocked_on" in results:
        logger.info(f"BLOCKED: {results['blocked_on']}")

    v16 = results.get("v16_audit", {})
    logger.info("-" * 80)
    logger.info("V16 Audit:")
    logger.info(f"  Non-vacuity: {v16.get('non_vacuity', False)}")
    logger.info(f"  No post-hoc tuning: {v16.get('no_posthoc_tuning', False)}")
    logger.info(f"  Correct reference: {v16.get('correct_reference', 'N/A')}")
    logger.info(f"  Runnable independently: {v16.get('runnable_independently', False)}")
    logger.info("=" * 80)

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

