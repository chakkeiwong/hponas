# V14 Protocol: Day-One Walk Reproduction

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

Tier 0 is "composition, not construction" - day-one walk example executes without errors and produces expected artifacts.

**Operational requirement:** Chapter 15 end-to-end example must be reproducible for users.

---

## Hypothesis

### H0 (Null Hypothesis)
Not applicable - this is a **deterministic reproduction check**, not a statistical test.

### H1 (Alternative Hypothesis)
Not applicable - this is a **deterministic reproduction check**, not a statistical test.

### Test Type
**Hard veto** - pass/fail on deterministic criteria. Consumes no alpha, not part of family correction.

---

## Preregistration

### Test Scenario
**Script:** examples/v14_day_one_walk.py (or equivalent path)

**Expected behavior:**
1. Script executes without errors
2. Database created: v14_walk.db
3. Checkpoints directory created: v14_checkpoints/
4. At least one trial executed (non-vacuous)
5. Protected test seed (999) never reaches searcher (seed isolation verified)

### Seeds
**Protected seed:** 999 (must never appear in trials table)

**Training seeds:** Implementation-dependent (any seeds except 999)

### Pass Criteria

**All of the following must be true:**
1. Script returns exit code 0 (no exceptions)
2. Database file exists and is non-empty
3. Checkpoints directory exists
4. trials table has n_trials > 0 (non-vacuous execution)
5. Protected seed 999 not in trials.seed column

### Timeout
**Maximum execution time:** 60 seconds

**Rationale:** Day-one walk should be fast demonstration, not full optimization.

---

## Decision States

### PASS
**All of the following must be true:**
1. Executed successfully (exit code 0)
2. Artifacts present (db, checkpoints)
3. Trials executed (n_trials > 0)
4. Seed isolated (999 not in trials)
5. V16 audit: non-vacuous

### FAIL
**Any of the following:**
1. Script raises exception
2. Missing artifacts
3. Zero trials executed (vacuous pass)
4. Seed isolation violated (999 in trials)
5. Timeout (>60s)
6. V16 audit fails

### INCONCLUSIVE
**Any of the following:**
1. Script not found
2. Dependencies missing
3. Platform incompatibility

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v14_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v14_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v14",
    "timestamp": "ISO8601",
    "executed_successfully": bool,
    "artifacts_present": bool,
    "trials_executed": bool,
    "n_trials": int,
    "seed_isolated": bool,
    "passed": bool,
    "execution_time_seconds": float,
    "script_path": "examples/v14_day_one_walk.py",
    "db_path": "./v14_walk.db",
    "checkpoint_dir": "./v14_checkpoints",
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Artifacts (Test Outputs)
- **Database:** v14_walk.db (cleaned up after validation)
- **Checkpoints:** v14_checkpoints/ (cleaned up after validation)

### Log
- **Path:** validation/results/v14_log.txt
- **Format:** Append-only text log

---

## Implementation

### Scripts
- **Main:** validation/v14_day_one_walk.py (existing)
- **Target:** examples/v14_day_one_walk.py (script being validated)
- **Validator:** validation/validators/v14_validator.py (V16-compliant)

### Execution
```python
# Run day-one walk script
result = subprocess.run(
    [sys.executable, "examples/v14_day_one_walk.py"],
    capture_output=True,
    timeout=60,
    check=True
)

# Check artifacts
assert Path("v14_walk.db").exists()
assert Path("v14_checkpoints").exists()

# Check seed isolation
conn = sqlite3.connect("v14_walk.db")
trial_seeds = [row[0] for row in conn.execute("SELECT seed FROM trials")]
assert len(trial_seeds) > 0, "Non-vacuous: at least one trial executed"
assert 999 not in trial_seeds, "Seed isolation: protected seed 999 never in trials"
```

### Dependencies
- sqlite3 (Python stdlib)
- hponas (core package)

---

## Known Issues

### Issue 1: Vacuous Pass (FIXED)
**Problem:** Original implementation passed on zero trials (vacuous).

**Resolution:** validation/v14_day_one_walk.py lines 139-161 now require n_trials > 0.

**Status:** Fixed 2026-09-02.

### Issue 2: Script Location
**Problem:** Script may be at examples/ or validation/ depending on repo structure.

**Resolution:** Protocol allows flexible path, validation script auto-detects.

**Status:** Handled in implementation.

### Issue 3: Cleanup
**Problem:** Artifacts left on disk after validation.

**Resolution:** Validation script cleans up on PASS, leaves artifacts on FAIL for debugging.

**Status:** Implemented.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] At least one trial executed (n_trials > 0)
- [ ] Database not empty
- [ ] Validator fails on zero-trial run

### Check 2: No Post-Hoc Tuning
- [ ] Protected seed (999) preregistered
- [ ] Pass criteria preregistered (not adjusted after run)

### Check 3: Correct Reference
- [ ] Not applicable (reproduction check, no reference)

### Check 4: Runnable Independently
- [ ] Script runs without manual intervention
- [ ] Results written atomically
- [ ] Artifacts cleaned up on pass

---

## References

**Authority:**
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 824-831 (V14 repair)
- protocols.json lines 20-24 (V14 as deterministic reproduction check)

**Implementation:**
- validation/v14_day_one_walk.py (existing)

**Related Protocols:**
- V02 (state replay, also deterministic)
- V03 (mutation testing, also deterministic)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- Deterministic reproduction check (not statistical test)
- Protected seed: 999
- Timeout: 60 seconds
- Non-vacuity: n_trials > 0 required
- Documents vacuous pass fix (2026-09-02)

---

**END OF PROTOCOL**
