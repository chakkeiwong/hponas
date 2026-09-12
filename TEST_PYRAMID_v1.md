# Test Pyramid v1.0

**Date**: 2026-09-09  
**Status**: DRAFT  
**Authority**: HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 3 Day 4-5 deliverable  

---

## Purpose

This document defines the three-layer test strategy for HPO-NAS:

1. **Unit/Contract Tests** (Layer 0) - Fast, isolated, high-volume
2. **Integration Tests** (Layer 1) - Component interactions, medium coverage
3. **Statistical Validations** (Layer 2) - End-to-end properties, preregistered protocols

The pyramid ensures:
- Fast feedback loops (unit tests run in milliseconds)
- Comprehensive coverage (contracts verify all documented behaviors)
- Scientific rigor (validations use preregistered protocols with statistical tests)
- Efficient CI/CD (most tests run quickly, expensive tests run selectively)

---

## Layer 0: Unit & Contract Tests

### Purpose
Verify individual functions and classes conform to their documented contracts. Contracts are extracted from docstrings and tested programmatically.

### Characteristics
- **Speed**: < 1 second per test
- **Isolation**: No file I/O, no network, deterministic
- **Coverage**: 100% of public API surface
- **Frequency**: Every commit, pre-push hook

### Test Structure
```python
def test_contract_SearchSpace_sample_random_with_seed():
    """Contract: Same seed produces same config."""
    space = SearchSpace(parameters={
        'lr': Continuous(1e-4, 1e-1, log=True),
        'batch_size': Integer(16, 128, log=True)
    })
    
    c1 = space.sample_random(seed=42)
    c2 = space.sample_random(seed=42)
    
    assert c1 == c2, "Contract violation: determinism"
```

### Current Status
- **Total contracts**: 69 (from CONTRACT_TEST_INVENTORY.md)
- **Implemented**: 69 tests in `tests/contract/`
- **Passing**: 38/69 (55%)
- **Blocking failures**: 31 tests (documented in WEEK_2_3_PROGRESS_SUMMARY.md)

### Contract Categories
1. **Determinism** (15 contracts) - Seed control, reproducibility
2. **State management** (12 contracts) - Save/restore, serialization
3. **Bounds enforcement** (8 contracts) - Search space limits
4. **Type safety** (10 contracts) - Input validation, output types
5. **Configuration** (14 contracts) - Parameter handling, defaults
6. **History tracking** (10 contracts) - Observation logging, warmstart

### Automation
Contract tests are auto-discovered and run via pytest:
```bash
pytest tests/contract/ -v --tb=short
```

Pre-commit hook blocks commits if new contract violations are introduced.

---

## Layer 1: Integration Tests

### Purpose
Verify interactions between components work correctly in realistic scenarios.

### Characteristics
- **Speed**: 1-30 seconds per test
- **Scope**: Multiple classes, file I/O, serialization
- **Coverage**: Critical workflows (search loop, checkpoint resume, warmstart)
- **Frequency**: Pre-push, CI on PR

### Test Structure
```python
def test_integration_checkpoint_resume_continues_search():
    """Verify checkpoint resume continues from exact state."""
    # Setup: run 5 iterations, save checkpoint
    optimizer = Optimizer(searcher=SobolSearcher(...), ...)
    for _ in range(5):
        config = optimizer.suggest()
        optimizer.report(config, result=...)
    
    state = optimizer.get_state()
    
    # Resume: run 5 more iterations
    optimizer2 = Optimizer.from_state(state)
    for _ in range(5):
        config = optimizer2.suggest()
        optimizer2.report(config, result=...)
    
    # Verify: total 10 observations, correct history
    assert len(optimizer2.history) == 10
    assert optimizer2.history[:5] == optimizer.history
```

### Test Categories
1. **Search loop** - suggest() → report() → suggest() cycles
2. **Checkpoint resume** - Save state, restore, continue identically
3. **Warmstart** - Initialize searcher with prior observations
4. **Multi-fidelity** - Early stopping, fidelity promotion
5. **Serialization** - ConfigSpace save/load, state pickling
6. **Error handling** - Invalid inputs, corrupted state

### Current Status
- **Coverage**: Partial (legacy tests exist in `tests/integration/`)
- **Refactoring needed**: Update to new API (SearchSpace, suggest())
- **Target**: 25-30 integration tests covering critical paths

### Automation
```bash
pytest tests/integration/ -v --tb=short
```

---

## Layer 2: Statistical Validations

### Purpose
Verify high-level properties of the system using statistical tests and preregistered protocols.

### Characteristics
- **Speed**: 30 seconds - 10 minutes per validation
- **Scope**: End-to-end system behavior
- **Rigor**: Preregistered hypotheses, decision thresholds, immutable artifacts
- **Frequency**: Weekly, before releases, on-demand for specific claims

### Protocol Structure
Each validation follows the template:
1. **Claim** - Property being validated
2. **Hypothesis** - Testable prediction (with null hypothesis)
3. **Preregistration** - Analysis plan, decision thresholds, sample sizes
4. **Decision States** - PASS/FAIL/INCONCLUSIVE criteria
5. **Immutable Artifacts** - Preserved outputs (configs, distributions, p-values)
6. **Implementation** - Executable test script
7. **Known Issues** - Documented limitations
8. **V16 Audit Checklist** - Verification that protocol was followed

### Statistical Tests
- **Kolmogorov-Smirnov (KS)** - Distribution equivalence (determinism, parity)
- **Chi-square** - Categorical distribution tests
- **T-test** - Mean comparison (performance, efficiency)
- **ANOVA** - Multi-group comparison
- **Bootstrap CI** - Robust confidence intervals

### Validation Inventory

**Tier 0: Wrapper Correctness** (V01-V03, V14)
- V01: Wrapper parity (Sobol, GP determinism)
- V02: ConfigSpace serialization
- V03: Multi-fidelity determinism
- V14: Tabular backend (day-one walk reproduction)

**Tier 1: Search Semantics** (V04-V06)
- V04-T0: Early stopping correctness (termination)
- V04-T1: Early stopping correctness (promotion)
- V05: Warmstart correctness
- V06: Tabular interface contract

**Tier 2: System Properties** (V07-V13, V15)
- V07: Config hash stability
- V08: State save/restore fidelity
- V09: Search space bounds enforcement
- V10: Prior correctness (GP kernel)
- V11: Parallel safety (no race conditions)
- V12: Memory limits (resource bounds)
- V13: Error handling (graceful failures)
- V15: Kernel correctness (RBF, Matern)

### Current Status
- **Total protocols**: 15 (V01-V15)
- **Documented**: 15/15 (all in `validation/protocols/`)
- **Executed**: 1/15 (V01 PASSED)
- **Ready for execution**: 15/15 (audit complete per VALIDATION_PROTOCOL_AUDIT.md)

### Execution
```bash
# Run single validation
python validation/v01_wrapper_parity.py

# Run tier
python validation/run_tier.py --tier 0

# Run all validations
python validation/run_all.py
```

### Artifact Storage
All validation runs produce immutable artifacts:
```
validation/artifacts/
  v01_run_20260909_143022/
    protocol.md          # Copy of protocol at execution time
    configs.json         # Configurations generated
    distributions.json   # Statistical distributions
    results.json         # Test results (KS statistic, p-value, verdict)
    metadata.json        # Execution metadata (timestamp, seed, version)
```

---

## Test Selection Strategy

### Development Workflow
1. **Pre-commit**: Unit tests only (fast feedback)
2. **Pre-push**: Unit + integration tests (comprehensive local check)
3. **CI on PR**: Unit + integration + Tier 0 validations
4. **Weekly**: Full validation suite (all 15 protocols)
5. **Pre-release**: Full validation suite + manual spot checks

### Debugging Workflow
When a validation fails:
1. Check contract tests for the involved components
2. Check integration tests for the workflow
3. Inspect validation artifacts (distributions, configs)
4. Add unit/integration tests to cover the gap
5. Fix root cause
6. Re-run validation to confirm fix

### Coverage Targets
- **Unit/Contract**: 100% of public API
- **Integration**: 80% of critical workflows
- **Validation**: 15 preregistered protocols (fixed set)

---

## V16 Audit Enforcement

### Purpose
Ensure all validation executions follow their preregistered protocols without post-hoc modifications.

### Mechanism
The V16 validator audits each validation execution:
1. **Protocol immutability** - Protocol file unchanged since preregistration
2. **Decision adherence** - Verdict follows preregistered thresholds
3. **Artifact completeness** - All required outputs preserved
4. **Metadata correctness** - Execution details logged
5. **Known issues disclosure** - Limitations documented

### Implementation
Week 3 Day 6 deliverable: Add V16 audit checks to validator framework.

```python
class V16Auditor:
    def audit(self, validation_run):
        """Audit a validation run for protocol compliance."""
        checks = [
            self.check_protocol_immutability(validation_run),
            self.check_decision_adherence(validation_run),
            self.check_artifact_completeness(validation_run),
            self.check_metadata_correctness(validation_run),
            self.check_known_issues_disclosure(validation_run),
        ]
        
        return AuditResult(
            passed=all(c.passed for c in checks),
            checks=checks,
            timestamp=datetime.now()
        )
```

Every validation execution produces:
- `v01_run_*/results.json` - Test results
- `v01_run_*/v16_audit.json` - V16 audit results

V16 audit failures BLOCK validation PASS verdicts.

---

## Pyramid Metrics

### Test Count Distribution (Target)
```
Layer 2 (Validations):      15 tests  [     *     ]  (1%)
Layer 1 (Integration):      30 tests  [   *****   ]  (3%)
Layer 0 (Unit/Contract):   900 tests  [***********]  (96%)
```

### Execution Time Distribution (Target)
```
Layer 2 (Validations):    ~60 min  (10 min max per validation)
Layer 1 (Integration):    ~15 min  (30 sec max per test)
Layer 0 (Unit/Contract):  ~15 min  (1 sec max per test)
Total:                    ~90 min  (full suite)
```

### Current Metrics (2026-09-09)
```
Layer 2 (Validations):       1/15 executed (V01 PASSED)
Layer 1 (Integration):    ~20 tests (partial coverage)
Layer 0 (Unit/Contract):    69 tests (38 passing, 31 failing)
```

---

## Maintenance

### Adding New Tests

**New unit/contract test:**
1. Add contract to component docstring
2. Add test to `tests/contract/test_<component>.py`
3. Run `pytest tests/contract/` to verify
4. Update CONTRACT_TEST_INVENTORY.md

**New integration test:**
1. Identify workflow gap
2. Add test to `tests/integration/test_<workflow>.py`
3. Run `pytest tests/integration/` to verify
4. Document in this file (Layer 1 section)

**New validation:**
1. Write protocol in `validation/protocols/vXX_protocol.md`
2. Follow template (Claim, Hypothesis, Preregistration, etc.)
3. Implement test in `validation/vXX_<name>.py`
4. Add to validation inventory in this file
5. Run protocol audit (V16)

### Protocol Modifications
Validation protocols are **immutable after preregistration**. If a protocol needs changes:
1. Document why in protocol's Known Issues section
2. Create new protocol version (e.g., V01 → V01.1)
3. Preserve old protocol for historical runs
4. Update validation inventory

### Test Hygiene
- Unit tests: no file I/O, no network, deterministic
- Integration tests: use temp directories, clean up after
- Validations: preserve all artifacts, never mutate protocol

---

## References

- CONTRACT_TEST_INVENTORY.md - Full list of 69 contracts
- VALIDATION_PROTOCOL_AUDIT.md - Audit of V01-V15 protocol documents
- WEEK_2_3_PROGRESS_SUMMARY.md - Week 2 test results
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md - Overall recovery plan

---

## Changelog

### 2026-09-09
- Initial version (v1.0)
- Defined three-layer pyramid structure
- Documented 69 contract tests, ~30 integration tests, 15 validations
- Specified V16 audit enforcement mechanism
- Set coverage targets and execution time budgets
