# V07 Protocol: GPU Campaign Capacity

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** Program-level (not tier-specific)  

---

## Claim

Stated GPU budget is sufficient for all validation campaigns without exceeding capacity.

**Operational requirement:** Program feasibility depends on GPU availability matching campaign needs.

---

## Hypothesis

### H0 (Null Hypothesis)
Not applicable - this is a **resource audit**, not a statistical test.

### H1 (Alternative Hypothesis)
Not applicable - this is a **resource audit**, not a statistical test.

### Test Type
**Resource audit** - arithmetic verification. Consumes no alpha.

---

## Preregistration

### Audit Scope
Sum all validation GPU requirements across V01-V16:

**Known costs:**
- V04-T1: Real workload, 200 trials × 5 seeds × 10 min = ~167 GPU-hours
- V05: Real workload, 50 trials × 3 seeds × 10 min = ~25 GPU-hours
- V06: ASHA, completed (minimal GPU cost, synthetic)
- V07: This audit (no GPU cost)
- V08: BG-PBT flagship campaign (largest, TBD)
- V09: qLogNEHVI, completed (minimal GPU cost, synthetic)
- V11: Pilot completed (17.9 min total, CPU-only)
- Others: CPU-only or deferred

**Total estimated:** ~200+ GPU-hours minimum (before V08)

**Stated budget:** BUILD_PROGRAM_REVIEW_VERDICT.md line 733 notes "V07 alone needs 3.8 GPU-weeks but total budget claims 5."
- 3.8 GPU-weeks = 638 GPU-hours
- 5 GPU-weeks = 840 GPU-hours

### Pass Criteria

**PASS requires:**
1. Sum(GPU-hours across all validations) ≤ Available GPU capacity
2. No validation individually exceeds allocated budget
3. Reconciliation shows arithmetic consistency

**FAIL triggers:**
1. Sum exceeds capacity
2. V08 alone exceeds remaining budget after V04-T1/V05
3. Arithmetic contradictions (V07 needs 638h but total is 840h)

---

## Decision States

### PASS
**All of the following must be true:**
1. Total GPU-hours ≤ available capacity
2. Per-validation budgets reconcile
3. Contingency buffer (20-30%) included
4. V16 audit: non-vacuous, all campaigns counted

### FAIL
**Any of the following:**
1. Total exceeds capacity
2. Arithmetic contradictions detected
3. V08 campaign not budgeted

### INCONCLUSIVE
**Any of the following:**
1. V08 (BG-PBT) campaign size not yet determined
2. GPU availability not confirmed

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v07_protocol.md
- **Status:** Immutable after audit starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v07_results.json
- **Format:** JSON with per-validation GPU requirements, total, capacity

### Reconciliation Spreadsheet
- **Path:** WORK_BREAKDOWN_v3.xlsx (from Week 1 Day 1-3)
- **Columns:** Validation ID, GPU type, GPU count, GPU days, Total GPU-hours

---

## Implementation

### Scripts
- **Main:** validation/v07_gpu_capacity_audit.py (to be created)
- **Validator:** validation/validators/v07_validator.py (V16-compliant)

### Execution
```python
# Sum all validation GPU requirements
validations = {
    "V04-T1": 167,  # GPU-hours
    "V05": 25,
    "V08": TBD,  # Largest campaign
    # ... others
}

total_required = sum(validations.values())
available_capacity = 840  # 5 GPU-weeks

assert total_required <= available_capacity, "GPU budget exceeded"
```

---

## Known Issues

### Issue 1: V07 Alone Needs 3.8 GPU-Weeks
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md line 733: "V07 alone needs 3.8 GPU-weeks but total budget claims 5."

**Interpretation:** Unclear if "V07" refers to this audit or a different validation (possibly mislabeled V08 BG-PBT?).

**Resolution:** Week 1 Day 1-3 reconciliation clarifies which validation requires 3.8 GPU-weeks.

### Issue 2: V08 Not Sized Yet
**Problem:** BG-PBT flagship campaign size not determined.

**Resolution:** Week 4 Day 3 Tier 2 scope includes V08 sizing.

**Status:** V07 audit blocked until V08 sized.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] At least one validation with GPU requirement
- [ ] All V01-V16 counted (no missing entries)

### Check 2: No Post-Hoc Tuning
- [ ] Budget (5 GPU-weeks) preregistered in BUILD_PROGRAM
- [ ] Not adjusted after campaigns run

### Check 3: Correct Reference
- [ ] Not applicable (resource audit)

### Check 4: Runnable Independently
- [ ] Script sums GPU requirements and compares to budget
- [ ] Results written atomically

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md line 733 (GPU capacity conflict)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 767-774 (V07 repair)
- WORK_BREAKDOWN_v3.xlsx (Week 1 Day 1-3 deliverable)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Resource audit (not statistical test)
- Budget: 5 GPU-weeks (840 GPU-hours)
- Known conflict: V07 alone needs 3.8 GPU-weeks (interpretation TBD)
- V08 sizing pending

---

**END OF PROTOCOL**
