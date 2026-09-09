# V16 Protocol: Validator Audit (Meta-Validation)

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** All gates (Tier 0, 1, 2, distributed-beta)  

---

## Claim

All validators (V01-V15) are non-vacuous, not post-hoc tuned, with correct references, and runnable independently.

**Operational requirement:** Validator quality gates prevent false validation passes and post-hoc threshold tuning.

---

## Hypothesis

### H0 (Null Hypothesis)
Not applicable - this is a **meta-validation**, not a statistical test.

### H1 (Alternative Hypothesis)
Not applicable - this is a **meta-validation**, not a statistical test.

### Test Type
**Deterministic audit** - pass/fail on deterministic criteria. Consumes no alpha.

---

## Preregistration

### Audit Checks

Every validator V01-V15 must implement `--audit` mode and pass 4 checks:

#### Check 1: Non-Vacuity
**Criterion:** Validator fails on structurally empty input.

**Examples:**
- `validate(results=[])` → ERROR (not PASS)
- `validate(results=[{trials: 0}])` → ERROR (not PASS)
- `validate(n_trials=0)` → ERROR (not PASS)

**Test:** Feed empty input to validator, verify it raises error or returns FAIL (not PASS).

#### Check 2: No Post-Hoc Tuning
**Criterion:** Thresholds recorded before campaign, not adjusted after seeing results.

**Examples:**
- Protocol file preregisters `margin=0.05`, validator uses exactly 0.05
- Changing threshold after results → AUDIT FAIL
- Command-line threshold override → AUDIT FAIL

**Test:** Compare validator threshold to protocol file, verify exact match.

#### Check 3: Correct Reference
**Criterion:** Validator compares against declared vendor/baseline, not self.

**Examples:**
- V01 "GP matches BoTorch" must compare to BoTorch, not own GP
- V04 compares to random baseline, not to pathological config twice
- Tautological self-comparison → AUDIT FAIL

**Test:** Inspect validator implementation, verify reference source.

#### Check 4: Runnable Independently
**Criterion:** Full protocol executes standalone without human intervention.

**Examples:**
- `python validation/v06_asha_efficiency.py --audit` runs without input
- All parameters from protocol file (not command-line)
- Results written atomically

**Test:** Run validator with `--audit` flag, verify exit code 0 and output file.

---

## Decision States

### PASS
**All of the following must be true:**
1. All V01-V15 validators pass Check 1 (non-vacuity)
2. All V01-V15 validators pass Check 2 (no post-hoc tuning)
3. All V01-V15 validators pass Check 3 (correct reference)
4. All V01-V15 validators pass Check 4 (runnable independently)

### FAIL
**Any of the following:**
1. Any validator fails any check
2. V16 audit not implemented in validator

**Consequence:** Gate blocked until validator fixed.

### INCONCLUSIVE
**Any of the following:**
1. Validator not yet implemented
2. Protocol file missing or incomplete

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v16_protocol.md
- **Status:** Immutable
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v16_results.json
- **Format:** JSON with per-validator audit results

### Audit Reports
- **Per-validator:** `validation/results/v{XX}_audit.json`

---

## Implementation

### Base Validator
- **Path:** validation/validators/base_validator.py
- **Interface:**
  ```python
  class ValidationProtocol:
      def audit(self) -> AuditReport:
          """Run V16 audit checks."""
          checks = [
              self._check_non_vacuity(),
              self._check_no_posthoc_tuning(),
              self._check_correct_reference(),
              self._check_runnable_independently(),
          ]
          return AuditReport(checks=checks, passed=all(checks))
  ```

### Per-Validator Implementations
- **V01:** validation/validators/v01_validator.py
- **V02:** validation/validators/v02_validator.py
- ... (V03-V15)

### Execution
```bash
# Run V16 audit on all validators
python validation/v16_validator_audit.py

# Per-validator audit
python validation/v01_sobol_parity.py --audit
```

---

## Known Issues

### Issue 1: Not Implemented
**Status:** V16 audit protocol defined but validators not yet implemented.

**Resolution:** Week 3 Day 6 adds V16 audit implementation to every gate.

**Status:** To be implemented.

### Issue 2: V14 Vacuous Pass (FIXED)
**Example:** V14 originally passed on zero trials (vacuous).

**Resolution:** validation/v14_day_one_walk.py lines 139-161 now require n_trials > 0.

**Status:** Fixed 2026-09-02, serves as template for other validators.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] V16 itself fails on empty validator set
- [ ] At least one validator audited

### Check 2: No Post-Hoc Tuning
- [ ] Four audit checks defined before validators run
- [ ] Checks not adjusted after seeing results

### Check 3: Correct Reference
- [ ] Not applicable (meta-validation)

### Check 4: Runnable Independently
- [ ] `python validation/v16_validator_audit.py` runs standalone
- [ ] Produces v16_results.json

---

## References

**Authority:**
- BUILD_PROGRAM_v2.md lines 165-189 (V16 audit protocol specification)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 446-495 (V16 gate enforcement)
- validation/v14_day_one_walk.py lines 139-161 (non-vacuity fix example)

**Related:**
- All V01-V15 protocols include "V16 Audit Checklist" sections

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Four audit checks: non-vacuity, no post-hoc tuning, correct reference, runnable independently
- Enforced at all gates (Tier 0, 1, 2, distributed-beta)
- Base validator interface defined
- V14 vacuous pass documented as fixed example

---

**END OF PROTOCOL**
