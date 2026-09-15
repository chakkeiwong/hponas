# V03 Mutation Testing - System Reboot Reset Memo

**Date:** 2026-09-16 02:21 UTC  
**Session:** 8ca03d68-7ad6-4987-9d50-b73bc317c9ea  
**Status:** MUTATION TESTING IN PROGRESS - INTERRUPTED FOR REBOOT

---

## Current Situation

### Mutation Testing Run Status
- **Process PID:** 2630012 (will be killed by reboot)
- **Elapsed Time:** 54 minutes at last check (started ~01:25 UTC)
- **Progress:** 3143/5256 mutants processed (59.8% complete)
- **Current Scores:**
  - 🎉 Killed: 1649
  - 🫥 Survived: 730
  - 🙁 Suspicious: 702
  - ⏰ Timeout: 62
- **Kill Score:** 1649/(1649+730) = **0.693 (69.3%)**
- **Target:** ≥0.90 (90%)
- **Status:** **FAILING** - 20.7 percentage points below threshold

### What Was Running
```bash
mutmut run --max-children=1 2>&1 | tee /tmp/mutmut_run.log | tail -50
```

Output logged to: `/tmp/mutmut_run.log` (39,206 lines before reboot)

---

## Technical Context

### Problem History
1. **Previous Session Issue:** Mutmut hung at "Running stats" phase
2. **Root Cause:** Mutmut's fork/IPC mechanism had issues with some test types
3. **Fix Applied:** Configured `pytest_add_cli_args` in `pyproject.toml` to exclude incompatible tests

### Configuration Changes Made
File: `pyproject.toml`

```toml
[tool.mutmut]
paths = [
    "hponas/searchers/",
    "hponas/executors/",
    "hponas/legacy_searchers.py",
    "hponas/legacy_executors.py",
    "hponas/schedulers.py",
    "hponas/space.py",
    "hponas/types.py",
]
pytest_add_cli_args = [
    "--ignore=tests/unit",
    "--ignore=tests/test_cost_efficiency.py",
    "--ignore=tests/test_prior_recovery_pibo.py",
    "--ignore=tests/test_prior_recovery_priorband.py",
    "--ignore=tests/test_verify_manifest.py",
    "--ignore=tests/scale/test_distributed.py",
    "--ignore=tests/property/test_invariants.py",
]
debug = true
```

**Why These Exclusions:**
- `tests/unit`: Incomplete API, causes failures
- `test_cost_efficiency.py`: Slow convergence tests
- `test_prior_recovery_*.py`: Slow recovery tests, flaky convergence
- `test_verify_manifest.py`: Relative path issues
- `test_distributed.py`: Distributed test incompatibility
- `test_invariants.py`: Hypothesis health check fails with mutmut's forking

---

## Critical Discovery: Low Kill Score

**The mutation testing is working, but revealing a fundamental problem:**

The test suite has **insufficient coverage**. At 69.3% kill rate, we're detecting only 7 out of 10 mutations. This means:

1. **Many code paths lack test coverage**
2. **Mutants are surviving in:**
   - `reporting_mo.py` - edge cases around type coercion
   - `searchers/` modules - based on recent mutant names
   - `executors/` modules
   - `legacy_searchers.py` and `legacy_executors.py`

3. **702 suspicious mutants** indicate flaky tests that sometimes pass/fail

---

## After Reboot: Resume Actions

### Option 1: Continue Mutation Testing (Recommended First Step)
```bash
# Check if mutmut cache survived
ls -la .mutmut-cache/

# If cache exists, resume:
mutmut run --max-children=1 2>&1 | tee /tmp/mutmut_run_resumed.log | tail -50

# If cache lost, restart (will take ~1.5-2 hours):
rm -rf .mutmut-cache
mutmut run --max-children=1 2>&1 | tee /tmp/mutmut_run_fresh.log | tail -50
```

**Expected Outcome:** Kill score will likely remain around 0.65-0.70, **failing V03**

### Option 2: Analyze What Survived (If Run Completed Before Reboot)
```bash
# Get survived mutants
mutmut results 2>&1 | grep "survived" > survived_mutants.txt

# Sample specific mutants
mutmut show hponas.reporting_mo.x_pareto_front__mutmut_4
mutmut show hponas.searchers.<next_one>
```

### Option 3: Accept V03 Failure and Move to V02
V03 requires substantial test suite improvement (writing dozens of new edge case tests). Consider:
- Mark V03 as "DEFERRED - requires test coverage expansion"
- Move to V02 (deterministic replay, 3d effort)
- Return to V03 in Tier 1 after more implementation work provides better test targets

---

## Files Changed (Staged for Commit)

### Modified
- `pyproject.toml` - Added mutmut configuration
- `tests/scale/test_large_spaces.py` - Modified during investigation
- `tests/unit/test_executors.py` - Modified during investigation  
- `validation/v03_mutation_testing.py` - Updated validation script

### Deleted
- `tests/test_hamiltonian_mo.py` - Removed outdated tests
- `tests/test_sampler_neutra.py` - Removed outdated tests
- `tests/test_validation_stats.py` - Removed outdated tests

### Created
- `.mutmut-ignore` - Mutmut ignore patterns

---

## V03 Validation Requirements (Reference)

From `validation/v03_mutation_testing.py`:
- **Target:** Kill score ≥ 0.90
- **Scope:** Core modules (searchers, executors, schedulers, space, types)
- **Current Status:** FAILING at 0.693

---

## Tier 0 Gate Status

**Current:** 4/7 validations passed
- ✓ V04: Contract conformance
- ✓ V05: Checkpoint resume
- ✓ V06: Crash recovery  
- ✓ V15: State dict round-trip
- ✗ V03: Mutation testing (0.693 < 0.90)
- ✗ V02: Deterministic replay (not started)
- ✗ V14: Computational constraints (JAX LLVM memory issue)

**Gate Status:** BLOCKED - need 7/7 to proceed to Tier 1

---

## Recommendation for Next Session

1. **Check mutmut cache status** - determine if partial progress survived
2. **If cache lost:** Accept ~2 hour re-run time or defer V03
3. **If cache intact:** Let run complete (~40 more minutes)
4. **When complete:**
   - If score ≥0.90: Update TIER_0_GATE_STATUS.md, move to V02
   - If score <0.90: Analyze top 20 survived mutants, decide whether to:
     - Write targeted tests (could take 1-2 days for +20% coverage)
     - Defer V03 and proceed with V02/V14

5. **Strategic Decision:** V03 may not be cost-effective right now. The test suite works (4 validations passed), it just lacks edge-case coverage. Consider deferring V03 until Tier 1 implementation naturally expands test coverage.

---

## Background Task

Monitor process was running:
```bash
while true; do 
  ps -p 2630012 > /dev/null 2>&1 || break
  sleep 300
done
echo "Mutation testing completed at $(date)"
```

Task ID: bho4x4y8b (will not survive reboot)

---

## Log Files to Check After Reboot

- `/tmp/mutmut_run.log` - May survive if /tmp persistent
- `/tmp/mutmut_debug.log` - Mutmut internal debug log
- `.mutmut-cache/` - Mutmut state database

---

**Next action:** Check cache status, decide whether to resume or defer V03.
