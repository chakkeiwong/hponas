# V02 Protocol: Deterministic State Replay

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

Optimization runs are deterministic and reproducible from event logs. Given the same sequence of observations and random seed, the system produces identical suggestions.

**Operational requirement:** Debugging, auditing, and deterministic testing depend on replay correctness.

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

### Test Scenarios

**Scenario 1: Single searcher replay**
- Record 20-trial optimization run with GP+qLogEI
- Replay from event log with same seed
- Verify: all 20 suggestions identical (exact floating-point match)

**Scenario 2: Multi-fidelity scheduler replay**
- Record 30-trial ASHA run (3 fidelities, η=3)
- Replay from event log with same seed
- Verify: promotion/culling decisions identical, suggestions identical

**Scenario 3: Crash-resume replay**
- Run 50-trial optimization, kill process at trial 25
- Resume from checkpoint with same seed
- Verify: trials 26-50 identical to uninterrupted run

**Scenario 4: Concurrent events replay**
- Record distributed run with 4 parallel workers
- Replay from event log (events may arrive out-of-order)
- Verify: final state identical (order-invariant)

**Scenario 5: Zero-trial replay (vacuity check)**
- Attempt replay with empty event log
- Verify: test fails with clear error (not vacuous pass)

### Seeds
- Scenario 1: seed=42
- Scenario 2: seed=43
- Scenario 3: seed=44
- Scenario 4: seed=45, workers use 45+worker_id
- Scenario 5: seed=46 (empty log, should fail test)

### Pass Criteria

**All scenarios must satisfy:**
1. Suggestion identity: Every config field matches to machine precision
2. State identity: Searcher/scheduler internal state identical
3. Timing invariance: Replay produces same results regardless of wall-clock delays
4. Order invariance (Scenario 4 only): Out-of-order event arrival yields same final state

**Floating-point tolerance:**
- Exact match required (tolerance = 0.0)
- Rationale: Determinism means bit-identical, not "close enough"
- Exception: If random seed consumes platform entropy, document as known limitation

### Sample Size
- N/A (deterministic test, not statistical)
- Each scenario run once per seed

### Analysis
For each scenario:
```python
def verify_replay(original_suggestions, replayed_suggestions):
    if len(original_suggestions) != len(replayed_suggestions):
        return False, "Length mismatch"
    
    for i, (orig, replay) in enumerate(zip(original_suggestions, replayed_suggestions)):
        for key in orig:
            if orig[key] != replay[key]:  # Exact match
                return False, f"Mismatch at trial {i}, key {key}"
    
    return True, "Replay exact"
```

---

## Decision States

### PASS
**All of the following must be true:**
1. Scenarios 1-4: all suggestions identical (exact match)
2. Scenario 5: test fails with error (non-vacuous)
3. V16 audit: non-vacuous, runnable independently
4. Zero tolerance violations

### FAIL
**Any of the following:**
1. Any scenario 1-4: suggestion mismatch detected
2. Scenario 5: test passes on empty log (vacuous)
3. V16 audit fails
4. Platform non-determinism documented as limitation (see Known Issues)

### INCONCLUSIVE
**Any of the following:**
1. Replay infrastructure not yet implemented
2. Known platform limitation prevents determinism (e.g., GPU ops, external network)
3. Test cannot run (missing dependencies)

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v02_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v02_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v02",
    "timestamp": "ISO8601",
    "scenarios": [
      {
        "id": "scenario_1_single_searcher",
        "seed": 42,
        "n_trials": 20,
        "passed": bool,
        "mismatches": [],
        "notes": ""
      },
      ...
    ],
    "overall_passed": bool,
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Event Logs (Test Artifacts)
- **Path:** validation/results/v02_scenario{N}_events.jsonl
- **Format:** Newline-delimited JSON (append-only event log)
- **Content:** Each line: `{"timestamp": ISO8601, "event_type": "suggest|observe", "data": {...}}`

### Log
- **Path:** validation/results/v02_log.txt
- **Format:** Append-only text log
- **Content:** Per-scenario execution details, mismatch diagnostics

---

## Implementation

### Scripts
- **Main:** validation/v02_state_replay.py (to be created)
- **Validator:** validation/validators/v02_validator.py (V16-compliant)

### Test Structure
```python
class V02StateReplay:
    def test_single_searcher_replay(self, seed=42):
        # Run 20-trial GP+qLogEI, record events
        # Replay from log, verify suggestions identical
        ...
    
    def test_asha_replay(self, seed=43):
        # Run 30-trial ASHA, record events
        # Replay from log, verify promotions/culls identical
        ...
    
    def test_crash_resume(self, seed=44):
        # Run 50 trials, checkpoint at 25, kill, resume
        # Verify trials 26-50 match uninterrupted run
        ...
    
    def test_concurrent_replay(self, seed=45):
        # Distributed run with 4 workers, out-of-order events
        # Verify final state identical
        ...
    
    def test_vacuity(self, seed=46):
        # Empty event log should fail, not pass
        ...
```

### Dependencies
- hponas.searchers (GP+qLogEI)
- hponas.schedulers (ASHA)
- hponas.store (event log persistence)
- hponas.checkpoint (crash-resume)

---

## Known Issues

### Issue 1: Not Implemented
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md identified V02 as not implemented.

**Resolution:** Week 2 Day 1-5 created conformance tests (tests/conformance/test_checkpoint_resume.py), but full V02 protocol requires event log replay system.

**Status:** Blocked on event log infrastructure.

**Workaround:** Partial pass if checkpoint-resume determinism verified (Scenario 3 only).

### Issue 2: Platform Non-Determinism
**Problem:** Some operations may be non-deterministic:
- GPU floating-point operations (CUDA non-associative reductions)
- External network calls (latency-dependent)
- System clock reads

**Resolution:** 
- Document as known limitation
- CPU-only mode for deterministic replay
- Mock external calls in replay mode

**Status:** To be determined during implementation.

### Issue 3: Event Ordering Semantics
**Problem:** Concurrent observe() calls may arrive in different orders.

**Resolution:** Week 2 Day 6-7 defined event ordering semantics in CONTRACT_SEMANTICS_v1.md.

**Reference:** See "Event Ordering" section (lines 260-269 of master program).

**Status:** Semantics defined, implementation pending.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] Scenario 5 (zero-trial replay) fails with error
- [ ] At least one scenario has n_trials > 0
- [ ] Validator rejects empty event logs

### Check 2: No Post-Hoc Tuning
- [ ] Tolerance = 0.0 (exact match) hardcoded
- [ ] No command-line override of tolerance
- [ ] All scenarios preregistered (no scenario added after seeing results)

### Check 3: Correct Reference
- [ ] Not applicable (deterministic test, no reference implementation)

### Check 4: Runnable Independently
- [ ] `python validation/v02_state_replay.py` runs without manual intervention
- [ ] All parameters from protocol (seeds, n_trials, scenarios)
- [ ] Results written to validation/results/v02_results.json atomically

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md (V02 not implemented)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 721-726 (V02 repair specification)
- protocols.json lines 20-24 (V02 as deterministic veto, not statistical test)

**Related Protocols:**
- V03 (mutation testing, also deterministic)
- V14 (reproduction check, also deterministic)

**Related Implementations:**
- tests/conformance/test_checkpoint_resume.py (Week 2 Day 1-5, deterministic resume)
- CONTRACT_SEMANTICS_v1.md (event ordering, Week 2 Day 6-7)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- 5 scenarios: single searcher, ASHA, crash-resume, concurrent, vacuity
- Deterministic veto (not statistical test)
- Exact floating-point match required (tolerance=0.0)
- Preregistered seeds: 42, 43, 44, 45, 46
- Documents known issues: not implemented, platform non-determinism, event ordering

---

**END OF PROTOCOL**
