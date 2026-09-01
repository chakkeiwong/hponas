"""
V14 Day-One Walk: Chapter 15 end-to-end example executes without errors.

Survey reference: Ch 15 sec:day-one-walk.
Validation claim: Tier 0 is "composition, not construction" - assemble components to run HPO.

Protocol:
1. Execute examples/v14_day_one_walk.py
2. Verify no errors during execution
3. Verify expected artifacts produced (trials, checkpoints, observations)
4. Verify protected test seed never reached searcher (seed isolation)
5. Pass if all checks succeed

Success criteria:
- executed_successfully: True (no exceptions)
- artifacts_present: True (all expected files exist)
- seed_isolated: True (test seed never in searcher observations)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import sqlite3
import os


def v14_day_one_walk_validation(
    script_path: Path = None,
    cleanup: bool = True
) -> dict[str, any]:
    """
    V14: Test day-one walk reproduction.

    Args:
        script_path: Path to v14_day_one_walk.py (default: examples/v14_day_one_walk.py)
        cleanup: Remove artifacts after validation

    Returns:
        dict with keys: executed_successfully, artifacts_present, seed_isolated, passed
    """
    print(f"\n=== V14: Day-One Walk Validation ===")

    if script_path is None:
        script_path = Path(__file__).parent.parent / "examples" / "v14_day_one_walk.py"

    if not script_path.exists():
        return {
            "executed_successfully": False,
            "artifacts_present": False,
            "seed_isolated": False,
            "passed": False,
            "error": f"Script not found: {script_path}"
        }

    print(f"Script: {script_path}")

    # Expected artifacts
    db_path = Path("./v14_walk.db")
    checkpoint_dir = Path("./v14_checkpoints")

    # Clean up any existing artifacts from previous runs
    if db_path.exists():
        db_path.unlink()
    if checkpoint_dir.exists():
        import shutil
        shutil.rmtree(checkpoint_dir)

    # Execute script
    print("\nExecuting day-one walk script...")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True
        )

        executed_successfully = result.returncode == 0
        print(f"  Execution: {'✓ SUCCESS' if executed_successfully else '✗ FAILED'}")

        if not executed_successfully:
            print(f"  stderr: {result.stderr[:500]}")

    except subprocess.TimeoutExpired:
        print("  ✗ TIMEOUT (>60s)")
        return {
            "executed_successfully": False,
            "artifacts_present": False,
            "seed_isolated": False,
            "passed": False,
            "error": "Execution timeout"
        }
    except subprocess.CalledProcessError as e:
        print(f"  ✗ ERROR: {e}")
        print(f"  stderr: {e.stderr[:500]}")
        return {
            "executed_successfully": False,
            "artifacts_present": False,
            "seed_isolated": False,
            "passed": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"  ✗ EXCEPTION: {e}")
        return {
            "executed_successfully": False,
            "artifacts_present": False,
            "seed_isolated": False,
            "passed": False,
            "error": str(e)
        }

    # Check artifacts
    print("\nChecking artifacts...")
    artifacts_present = True

    if not db_path.exists():
        print(f"  ✗ Missing: {db_path}")
        artifacts_present = False
    else:
        print(f"  ✓ Found: {db_path}")

    if not checkpoint_dir.exists():
        print(f"  ✗ Missing: {checkpoint_dir}")
        artifacts_present = False
    else:
        print(f"  ✓ Found: {checkpoint_dir}")

    # Check seed isolation (protected test seed should never be in observations)
    print("\nChecking seed isolation...")
    seed_isolated = True
    protected_seed = 999  # From v14_day_one_walk.py

    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if protected seed appears in trial seeds
            cursor.execute("SELECT seed FROM trials")
            trial_seeds = [row[0] for row in cursor.fetchall()]

            if protected_seed in trial_seeds:
                print(f"  ✗ VIOLATION: Protected seed {protected_seed} found in trials")
                seed_isolated = False
            else:
                print(f"  ✓ Protected seed {protected_seed} never reached searcher")

            conn.close()

        except Exception as e:
            print(f"  ✗ ERROR checking seed isolation: {e}")
            seed_isolated = False
    else:
        seed_isolated = False

    # Overall pass/fail
    passed = executed_successfully and artifacts_present and seed_isolated

    print(f"\nOverall: {'✓ PASSED' if passed else '✗ FAILED'}")

    # Cleanup
    if cleanup and passed:
        print("\nCleaning up artifacts...")
        if db_path.exists():
            db_path.unlink()
        if checkpoint_dir.exists():
            import shutil
            shutil.rmtree(checkpoint_dir)

    return {
        "executed_successfully": executed_successfully,
        "artifacts_present": artifacts_present,
        "seed_isolated": seed_isolated,
        "passed": passed,
        "script_path": str(script_path),
        "db_path": str(db_path),
        "checkpoint_dir": str(checkpoint_dir),
    }


if __name__ == "__main__":
    print("="*70)
    print("V14 Day-One Walk Validation")
    print("="*70)

    result = v14_day_one_walk_validation(cleanup=True)

    print("\n" + "="*70)
    if result["passed"]:
        print("V14 VALIDATION: ✓ PASSED")
        print("Day-one walk executed successfully:")
        print("  ✓ No errors during execution")
        print("  ✓ All artifacts produced")
        print("  ✓ Protected test seed isolated from searcher")
    else:
        print("V14 VALIDATION: ✗ FAILED")
        if not result["executed_successfully"]:
            print("  ✗ Execution failed")
            if "error" in result:
                print(f"     Error: {result['error']}")
        if not result["artifacts_present"]:
            print("  ✗ Missing artifacts")
        if not result["seed_isolated"]:
            print("  ✗ Seed isolation violated")
    print("="*70)
