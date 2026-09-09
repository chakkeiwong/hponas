# V03 Protocol: Mutation Testing

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

The test suite detects real implementation bugs. A mutation testing kill score ≥0.90 demonstrates that tests catch meaningful code changes, not just pass on trivial inputs.

**Operational requirement:** Test suite quality gates depend on ability to detect regressions.

---

## Hypothesis

### H0 (Null Hypothesis)
Not applicable - this is a **deterministic veto**, not a statistical test.

### H1 (Alternative Hypothesis)
Not applicable - this is a **deterministic veto**, not a statistical test.

### Test Type
**Hard veto** - pass/fail on deterministic criteria. Consumes no alpha, not part of family correction.

---

## Preregistration

### Mutation Testing Tool
**Primary:** `mutmut` (Python mutation testing tool)  
**Fallback:** `cosmic-ray` (if mutmut unavailable)

### Target Code Modules
**In-scope for mutation testing:**
1. `hponas/searchers.py` - Core searcher implementations (GP+qLogEI, TPE, Random, Sobol)
2. `hponas/schedulers.py` - Core scheduler implementations (ASHA, MO-ASHA)
3. `hponas/acquisitions.py` - Acquisition functions (qLogEI, qLogNEHVI, EI-per-cost)
4. `hponas/space.py` - Search space handling (Knob, SearchSpace)
5. `hponas/executor.py` - Trial execution (LocalExecutor, RayExecutor)

**Out-of-scope:**
- CLI entry points (mutation would break imports)
- Visualization code (not decision-bearing)
- Deprecated/experimental code (not in Tier 0-1 scope)

### Mutation Operators
**Enabled operators (mutmut defaults):**
- Arithmetic: `+` → `-`, `*` → `/`, etc.
- Comparison: `<` → `<=`, `==` → `!=`, etc.
- Logical: `and` → `or`, `not` applied/removed
- Constants: `0` → `1`, `True` → `False`, etc.
- Return: `return x` → `return None`

**Disabled operators:**
- String mutations (not relevant for numerical code)
- Import mutations (too brittle)

### Kill Score Threshold
**Target:** ≥0.90 (90% of mutants killed)

**Justification:**
- Industry standard for high-quality test suites
- Lower threshold (0.70-0.80) insufficient for safety-critical claims
- 100% unrealistic due to equivalent mutants

**Equivalent Mutants:**
- Documented manually (mutants that don't change behavior)
- Excluded from denominator after review
- Maximum 5% equivalent mutant allowance

### Pass Criteria

**PASS requires all of:**
1. Kill score ≥0.90 across all in-scope modules
2. Zero survivors in critical paths (acquisition optimization, GP posterior, ASHA promotion logic)
3. Equivalent mutants documented and ≤5% of total
4. V16 audit: non-vacuous (at least 100 mutants generated)

**Per-module breakdown required:**
```
Module                  | Mutants | Killed | Survived | Timeout | Kill Score
hponas/searchers.py     |   150   |  138   |    8     |    4    |   0.92
hponas/schedulers.py    |   120   |  112   |    5     |    3    |   0.93
...
Total                   |   500   |  460   |   25     |   15    |   0.92
```

### Sample Size
- N/A (deterministic test, not statistical)
- Number of mutants determined by code size and mutation operators

### Analysis
```python
kill_score = killed_mutants / (total_mutants - equivalent_mutants - timeout_mutants)

# Per-module scores must also meet threshold
for module in in_scope_modules:
    assert module.kill_score >= 0.90
```

---

## Decision States

### PASS
**All of the following must be true:**
1. Overall kill score ≥0.90
2. All in-scope modules individually ≥0.90
3. Zero survivors in critical paths (manually reviewed)
4. Equivalent mutants documented and ≤5%
5. V16 audit: ≥100 mutants generated (non-vacuous)

### FAIL
**Any of the following:**
1. Overall kill score <0.90
2. Any in-scope module <0.90
3. Survivors found in critical paths
4. Equivalent mutants >5% or not documented
5. V16 audit fails (too few mutants, vacuous)

### INCONCLUSIVE
**Any of the following:**
1. Mutation tool not available or misconfigured
2. Timeout rate >20% (mutants hang, not killed or survived)
3. Code modules not yet implemented (Week 2 conformance tests incomplete)

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v03_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v03_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v03",
    "timestamp": "ISO8601",
    "tool": "mutmut",
    "tool_version": "2.4.0",
    "overall": {
      "total_mutants": 500,
      "killed": 460,
      "survived": 25,
      "timeout": 15,
      "equivalent": 12,
      "kill_score": 0.92,
      "passed": true
    },
    "per_module": [
      {"module": "hponas/searchers.py", "kill_score": 0.92, "killed": 138, "survived": 8, ...},
      ...
    ],
    "critical_survivors": [],
    "equivalent_mutants": [
      {"id": 42, "location": "searchers.py:123", "reason": "Dead code branch", "reviewed_by": "..."},
      ...
    ],
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Mutant Report
- **Path:** validation/results/v03_mutants.html
- **Format:** HTML report from mutmut
- **Content:** Per-mutant details, source diffs, test results

### Log
- **Path:** validation/results/v03_log.txt
- **Format:** Append-only text log
- **Content:** Mutation run timestamps, test suite execution log

---

## Implementation

### Scripts
- **Main:** validation/v03_mutation_testing.py (to be created)
- **Validator:** validation/validators/v03_validator.py (V16-compliant)

### Execution Command
```bash
# Generate mutants
mutmut run --paths-to-mutate=hponas/searchers.py,hponas/schedulers.py,hponas/acquisitions.py,hponas/space.py,hponas/executor.py

# Generate report
mutmut html

# Parse results
python validation/v03_mutation_testing.py --report .mutmut-cache/ --output validation/results/v03_results.json
```

### Test Suite Requirements
**Prerequisite:** Tier 0 test suite must exist before V03 can run.

**Expected coverage:**
- tests/unit/ - Unit tests for individual functions
- tests/conformance/ - Contract conformance tests (from Week 2 Day 1-5)
- tests/integration/ - Multi-component interaction tests

**Minimum test count:** >100 tests (from TEST_PYRAMID_v1.md Layer 1)

### Dependencies
- mutmut>=2.4.0 (or cosmic-ray>=8.0.0 fallback)
- pytest>=7.0.0 (test runner)
- coverage>=6.0.0 (for test coverage analysis)

---

## Known Issues

### Issue 1: Not Implemented
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md identified V03 as not implemented.

**Resolution:** Week 2 Day 1-5 created conformance tests. Week 3 Day 1-3 adds mutation testing protocol.

**Status:** Blocked on Tier 0 test suite completion (Week 2 Day 1-5 deliverable).

**Dependency:** Cannot run V03 until tests exist.

### Issue 2: Equivalent Mutants
**Problem:** Some mutants are semantically equivalent (don't change behavior).

**Resolution:**
- Manual review required
- Document each equivalent mutant with justification
- Maximum 5% allowance
- If >5%, improve test granularity

**Example equivalent mutants:**
- Dead code branches
- Redundant conditionals
- Logging/debug statements

### Issue 3: Timeout Mutants
**Problem:** Some mutants may cause infinite loops or hang.

**Resolution:**
- Set mutmut timeout to 60 seconds per mutant
- Timeout mutants excluded from kill score denominator
- If timeout rate >20%, investigate (likely test suite issue)

**Status:** Timeout threshold preregistered at 20%.

### Issue 4: Critical Path Definition
**Problem:** "Zero survivors in critical paths" requires defining critical paths.

**Critical paths (preregistered):**
1. Acquisition function optimization (acquisitions.py optimize_*)
2. GP posterior computation (searchers.py GP.posterior)
3. ASHA promotion logic (schedulers.py ASHA.promote)
4. qLogNEHVI hypervolume improvement (acquisitions.py qLogNEHVI._compute_hv)
5. Trial execution error handling (executor.py execute_trial)

**Resolution:** Any survivor in these functions/methods triggers FAIL.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] At least 100 mutants generated
- [ ] At least one in-scope module has mutants
- [ ] Test suite runs and produces results (not all skipped)
- [ ] Validator fails if zero mutants generated

### Check 2: No Post-Hoc Tuning
- [ ] Kill score threshold (0.90) preregistered in protocol
- [ ] Equivalent mutant threshold (5%) preregistered in protocol
- [ ] In-scope modules preregistered (not selected after seeing scores)
- [ ] Mutation operators preregistered (not adjusted after run)

### Check 3: Correct Reference
- [ ] Not applicable (deterministic test, no reference implementation)

### Check 4: Runnable Independently
- [ ] `python validation/v03_mutation_testing.py` runs without manual intervention
- [ ] All parameters from protocol (threshold, modules, operators)
- [ ] Results written to validation/results/v03_results.json atomically
- [ ] Equivalent mutants documented with reviewers

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md (V03 not implemented)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 727-732 (V03 repair specification)
- protocols.json lines 20-24 (V03 as deterministic veto, not statistical test)

**Industry Standards:**
- Mutation testing kill score ≥0.90 (high-quality test suite benchmark)
- Equivalent mutant allowance ≤5% (research consensus)

**Related Protocols:**
- V01 (vendor parity, shares test infrastructure)
- V02 (state replay, also deterministic veto)
- V14 (reproduction check, also deterministic veto)

**Related Implementations:**
- tests/conformance/ (Week 2 Day 1-5, prerequisite test suite)
- TEST_PYRAMID_v1.md (Week 3 Day 4-5, test design document)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- Kill score threshold: ≥0.90
- In-scope modules: searchers, schedulers, acquisitions, space, executor
- Equivalent mutant allowance: ≤5%
- Critical paths defined: 5 functions/methods with zero survivors required
- Timeout threshold: ≤20%
- Mutation tool: mutmut (primary), cosmic-ray (fallback)
- Documents known issues: not implemented, equivalent mutants, timeouts, critical path definition

---

**END OF PROTOCOL**
