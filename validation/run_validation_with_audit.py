#!/usr/bin/env python3
"""
Validation runner with V16 audit enforcement.

Wraps validation executions with V16 audit checks, ensuring all validation
runs comply with preregistered protocols and audit requirements.

Usage:
    python validation/run_validation_with_audit.py v04_t0
    python validation/run_validation_with_audit.py v05
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from validation.v16_audit_enforcer import V16Enforcer


class ValidationRunner:
    """Run validation with V16 audit enforcement."""

    def __init__(self, validation_id: str):
        self.validation_id = validation_id
        self.protocol_path = self._find_protocol()
        self.enforcer = V16Enforcer(self.protocol_path)

        # Create run directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(f"validation/artifacts/{validation_id}_run_{timestamp}")
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def _find_protocol(self) -> Path:
        """Locate protocol file for validation ID."""
        # Try v04_t0_protocol.md format
        candidates = [
            Path(f"validation/protocols/{self.validation_id}_protocol.md"),
            Path(f"validation/protocols/{self.validation_id.replace('-', '_')}_protocol.md"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            f"Protocol not found for {self.validation_id}. "
            f"Searched: {[str(c) for c in candidates]}"
        )

    def run(self, validation_fn: Callable[[], dict[str, Any]]) -> bool:
        """
        Execute validation with V16 audit.

        Args:
            validation_fn: Callable that runs the validation and returns results dict

        Returns:
            True if validation and audit both pass
        """
        print(f"=== Running {self.validation_id} with V16 audit ===")
        print(f"Protocol: {self.protocol_path}")
        print(f"Run directory: {self.run_dir}")
        print()

        # Step 1: Save protocol snapshot
        protocol_snapshot = self.run_dir / "protocol.md"
        shutil.copy(self.protocol_path, protocol_snapshot)
        print(f"✓ Protocol snapshot saved: {protocol_snapshot}")

        # Step 2: Execute validation
        print(f"\nExecuting validation...")
        try:
            results = validation_fn()
        except Exception as e:
            print(f"✗ Validation execution failed: {e}")
            return False

        # Step 3: Save results
        results_file = self.run_dir / "results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"✓ Results saved: {results_file}")

        # Step 4: Save execution metadata
        metadata = {
            'validation_id': self.validation_id,
            'timestamp': datetime.now().isoformat(),
            'protocol_path': str(self.protocol_path),
            'run_dir': str(self.run_dir),
        }
        metadata_file = self.run_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"✓ Metadata saved: {metadata_file}")

        # Step 5: Run V16 audit
        print(f"\n=== Running V16 audit ===")
        audit_result = self.enforcer.audit_execution(self.run_dir)

        # Save audit report
        audit_file = self.run_dir / "v16_audit.json"
        with open(audit_file, 'w') as f:
            json.dump(audit_result.to_dict(), f, indent=2)

        audit_txt = self.run_dir / "v16_audit.txt"
        with open(audit_txt, 'w') as f:
            f.write(str(audit_result))

        print(audit_result)
        print(f"\nAudit report saved: {audit_file}")

        # Step 6: Decision
        if not audit_result.passed:
            print(f"\n✗ V16 AUDIT FAILED - Results rejected")
            return False

        validation_passed = results.get('passed', False)
        if not validation_passed:
            print(f"\n⚠ Validation did not pass, but V16 audit OK")
            print(f"  This is an honest FAIL - results are valid but claim not supported")
            return False

        print(f"\n✓ VALIDATION PASSED with V16 compliance")
        return True


def main():
    parser = argparse.ArgumentParser(description="Run validation with V16 audit")
    parser.add_argument('validation_id', help='Validation ID (e.g., v04_t0, v05)')
    args = parser.parse_args()

    runner = ValidationRunner(args.validation_id)

    # For demonstration, we would import and run the actual validation function
    # For now, just show the structure
    print(f"ValidationRunner ready for {args.validation_id}")
    print(f"To complete integration:")
    print(f"  1. Import validation function (e.g., from validation.v04_t0_baseline_floor import run_check)")
    print(f"  2. Call runner.run(run_check)")
    print(f"  3. Validation executes with full V16 audit")


if __name__ == '__main__':
    main()
