# Tier 0 Execution Master Program v1.0

**Version:** 1.0  
**Date:** 2026-09-10  
**Status:** ACTIVE (Day 1 audit complete, issues found)  
**Authority:** BUILD_PROGRAM_v3.md Tier 0 section (lines 49-348)  
**Duration:** 25 days (8d baseline + 17d remediation)  
**Purpose:** Govern Tier 0 execution to prevent repeat of RED verdict  

---

## CRITICAL: Read This First After Context Compaction

This document governs ALL Tier 0 execution work. After context compaction:

1. Read this file FIRST
2. Check "Current Phase Marker" section below
3. Read "LAST COMPLETED" to understand progress
4. Read "NEXT TASK" to know what to do
5. Execute task following quality gates
6. Update phase marker after completion
7. Never skip quality gates or audits

**This program exists because we found critical issues in Day 1 work that could repeat the RED verdict pattern.**

---

## Current Phase Marker

**PHASE:** Phase 1 Day 4 - rl_routine Workload  
**DAY:** 1.4 (Last required baseline component)  
**LAST COMPLETED:** Phase 1 Day 3 complete - RayExecutor audited, 2 real defects fixed (dict-instead-of-Result contract violation, unused max_retries) + dead placeholder removed. 24 tests, 84% coverage. Total: 129 tests passing  
**NEXT TASK:** rl_routine workload (9-knob RL search space, Brax Ant) - first verify jax/brax availability in this environment  
**BLOCKED BY:** None (jax/brax dependency availability unverified)  
**DATE:** 2026-09-11  

**Update this section after completing each phase's work.**

---

## Tier 0 Overview

**Goal:** Establish minimal viable baseline with validated correctness

**Total Duration:** 29 days (revised from 25 days)
- **Phase 0:** Audit-Fix-Reaudit Cycle (4 days)
- **Phase 1:** Baseline Implementation (8 days)
- **Phase 2:** Remediation (17 days)

**Structure:** All work follows audit-execute-audit cycle to prevent drift

**Gate Criteria:** All of V01, V02, V03, V04-T0, V05, V14, V16 PASS with honest verdict

**Authority:** BUILD_PROGRAM_v3.md lines 49-348

---

## Phase Structure (Audit-Execute-Audit)

Every phase follows this pattern:
1. **Audit (before):** What's the current state? What needs to be done?
2. **Execute:** Do the work following quality gates
3. **Audit (after):** Did we do what we said? Any issues?
4. **Phase Marker Update:** Document completion, update next task

This structure prevents drift after context compaction by making audits part of the plan, not ad-hoc.

---

## Day 1 Audit Results (BLOCKING)

**Audit Date:** 2026-09-10  
**Audit File:** TIER0_DAY1_AUDIT.md  
**Verdict:** ⚠️ INCOMPLETE - CRITICAL ISSUES FOUND

### 🔴 Blocking Issues (Must Fix)

1. **GP+qLogEI `_prepare_training_data()` raises NotImplementedError**
   - File: `hponas/searchers/gp_searcher.py` line 127
   - Impact: Non-functional after 5 trials
   - Fix: Implement config-result mapping
   - Effort: 0.5-1 day

2. **Study class not verified**
   - File: `hponas/study.py`
   - Impact: Unknown if provides what GP needs
   - Fix: Audit Study implementation
   - Effort: 0.5 day

3. **Zero verified tests for Day 1 code**
   - Impact: No quality gate
   - Fix: Write unit tests
   - Effort: 1 day

### 🟡 Warning Issues (Should Fix)

4. Old code conflicts with new code (cleanup needed)
5. Specification violations not checked against old code
6. Item 9 incomplete (4/6): missing git hash, clean-install test

**Total Fix Effort:** 2-3 days

**Decision Required:** Fix now OR proceed with documented risks

---

## Quality Gates (Mandatory for All Days)

### Gate 1: Specification Compliance

**Before writing ANY code:**
- [ ] Identify LaTeX specification section
- [ ] Read specification requirements
- [ ] Check TRACEABILITY_MATRIX_v1.md for known violations
- [ ] Document which spec section this implements

**After writing code:**
- [ ] Implementation matches LaTeX algorithm
- [ ] No deviation from specification without explicit approval
- [ ] Defaults match preregistered values

**Rationale:** 15+ specification violations caused RED verdict

### Gate 2: Test Coverage

**Before marking task complete:**
- [ ] Unit tests written for all new functions/classes
- [ ] Tests pass locally
- [ ] Coverage >80% for new code
- [ ] Property tests for randomized components
- [ ] Edge cases covered (NaN, inf, empty, boundaries)

**Rationale:** "Zero executable product tests" caused RED verdict

### Gate 3: Integration Verification

**Before moving to next component:**
- [ ] Component integrates with dependencies
- [ ] End-to-end test demonstrates usage
- [ ] No NotImplementedError or TODO without plan
- [ ] All public APIs have tests

**Rationale:** GP+qLogEI was "complete" but had NotImplementedError

### Gate 4: Audit Trail

**After each day's work:**
- [ ] Update progress tracker (TIER0_PROGRESS.md)
- [ ] Update phase marker in this file
- [ ] Document any deviations or blockers
- [ ] Commit changes with descriptive message

**Rationale:** Context drift prevention (learned from recovery program)

### Gate 5: No Regression

**Before committing:**
- [ ] All existing tests still pass
- [ ] No new specification violations introduced
- [ ] Old code cleaned up or namespaced
- [ ] Documentation updated

**Rationale:** Don't break what works

---

## Phase 0: Audit-Fix-Reaudit Cycle (4 days)

**Purpose:** Fix critical issues found in Day 1 audit before proceeding with baseline implementation

**Authority:** TIER0_DAY1_AUDIT.md

### Phase 0 Day 1: Initial Audit [COMPLETE]

**Status:** ✅ COMPLETE

**Deliverables:**
- ✅ TIER0_DAY1_AUDIT.md created
- ✅ Critical issues identified
- ✅ Blocking issues documented
- ✅ Fix effort estimated (2-3 days)

**Findings:**
- 🔴 GP+qLogEI has NotImplementedError
- 🔴 Study class not verified
- 🔴 Zero verified tests
- 🟡 Old code conflicts
- 🟡 Specification violations not checked

**Next:** Phase 0 Day 2-4 (Fixes)

### Phase 0 Day 2-4: Fix Critical Issues [CURRENT]

**Duration:** 2-3 days

**Blocking Issue #1: Fix GP+qLogEI Implementation (0.5-1 day)**

**Problem:** `_prepare_training_data()` raises NotImplementedError (line 127)

**Root Cause:** No mapping from trial_id to config

**Fix Options:**
1. **Option A (Recommended):** Store trial-config mapping in BaseSearcher
   - Add `self.trials: Dict[str, Config] = {}` to BaseSearcher
   - In `suggest()`, store: `self.trials[trial_id] = config`
   - In `_prepare_training_data()`, retrieve: `config = self.trials[result.trial_id]`
   
2. **Option B:** Pass configs through Result
   - Add `config: Config` field to Result dataclass
   - Study passes config when creating Result
   - GP retrieves directly from result.config

**Chosen:** Option A (cleaner separation, Study already creates trial_id)

**Implementation:**
```python
# hponas/searchers/base.py
class BaseSearcher(ABC):
    def __init__(self, search_space: SearchSpace, seed: Optional[int] = None):
        self.search_space = search_space
        self.seed = seed
        self.history: List[Result] = []
        self.trials: Dict[str, Config] = {}  # ADD THIS
        
# hponas/searchers/gp_searcher.py
def suggest(self) -> Config:
    config = self.search_space.sample_random(...)
    # Generate trial_id to store mapping
    trial_id = f"trial_{len(self.trials)}"
    self.trials[trial_id] = config  # ADD THIS
    return config

def _prepare_training_data(self, results: list) -> tuple:
    X_list = []
    Y_list = []
    
    for result in results:
        # Retrieve config from stored mapping
        if result.trial_id not in self.trials:
            continue  # Skip if not found
        config = self.trials[result.trial_id]
        
        # Convert to tensors
        x = self._config_to_tensor(config)
        y = torch.tensor([result.objective_value], dtype=torch.float64)
        X_list.append(x)
        Y_list.append(y)
    
    X_train = torch.stack(X_list)
    Y_train = torch.stack(Y_list).unsqueeze(-1)
    return X_train, Y_train
```

**Quality Gates:**
- [ ] Implementation matches fix design
- [ ] No NotImplementedError remains
- [ ] Test: GP runs for >5 trials without crash

**Blocking Issue #2: Audit Study Class (0.5 day)**

**Task:** Verify Study class provides what GP needs

**Audit Checklist:**
- [ ] Study creates unique trial_id for each trial
- [ ] Study passes trial_id to Result
- [ ] Study calls searcher.suggest() → searcher.observe(result)
- [ ] Study doesn't interfere with searcher's trial tracking
- [ ] Study checkpoint includes searcher state

**If issues found:** Fix or redesign interface

**Quality Gates:**
- [ ] Study implementation reviewed
- [ ] Study + GPSearcher integration verified
- [ ] No blocking issues found

**Blocking Issue #3: Write Unit Tests (1 day)**

**Required Tests:**

**tests/unit/test_types.py:**
```python
def test_config_creation():
def test_config_getitem():
def test_trial_to_dict():
def test_result_is_valid():
def test_result_is_valid_nan():
def test_result_is_valid_failed():
def test_search_space_sample_random():
def test_search_space_validate_config():
def test_search_space_dim():
```

**tests/unit/test_gp_searcher.py:**
```python
def test_gp_searcher_initial_random():
def test_gp_searcher_suggest_after_5():
def test_gp_searcher_config_to_tensor():
def test_gp_searcher_tensor_to_config_roundtrip():
def test_gp_searcher_prepare_training_data():
def test_gp_searcher_state_serialization():
```

**tests/integration/test_study_gp.py:**
```python
def test_study_with_gp_on_branin():
    # End-to-end: 20 trials on Branin function
    # Verify: no crashes, best value improves
```

**Quality Gates:**
- [ ] All tests written
- [ ] All tests pass
- [ ] Coverage >80% for types.py, gp_searcher.py
- [ ] pytest exits 0

**Warning Issue #4: Clean Up Old Code (0.5 day)**

**Task:** Remove or namespace old code to prevent import conflicts

**Files to audit:**
- `hponas/searchers_gp.py` (old?) vs `hponas/searchers/gp_searcher.py` (new)
- `hponas/searchers.py` (old?) vs `hponas/searchers/` (new package)
- `hponas/searchers_priorband.py` (old, has specification violations)
- `hponas/priors.py` (old)
- `hponas/warm_start.py` (old, has specification violations)

**Action:**
1. Check if old files are used by validation scripts
2. If used: leave but add comment "# OLD CODE - DO NOT USE IN NEW IMPLEMENTATIONS"
3. If not used: delete or move to `hponas/legacy/`
4. Update `hponas/__init__.py` to only export new implementations

**Quality Gates:**
- [ ] Import paths clear (no ambiguity)
- [ ] Old code documented or removed
- [ ] No import errors

**Warning Issue #5: Check Specification Violations (0.5 day)**

**Task:** Verify old code violations not replicated in new code

**Audit against TRACEABILITY_MATRIX_v1.md:**
- [ ] πBO: Check if any code uses GP mean as weight (WRONG)
- [ ] PriorBand: Check if any code uses top-K promotion (WRONG)
- [ ] ifBO: Check if any code uses custom power-law (WRONG)
- [ ] Warm-start: Check if any code builds RGPE immediately (WRONG)

**Action:** Document findings, ensure new code doesn't repeat violations

**Quality Gates:**
- [ ] All old violations documented
- [ ] New code verified clean
- [ ] No specification violations in Phase 0 work

### Phase 0 Day 5: Re-Audit [NEXT AFTER FIXES]

**Purpose:** Verify all critical issues resolved before proceeding to Phase 1

**Audit Checklist:**

**1. GP+qLogEI:**
- [ ] `_prepare_training_data()` implemented (no NotImplementedError)
- [ ] GP runs for >5 trials without crash
- [ ] Integration test passes

**2. Study class:**
- [ ] Audit completed
- [ ] No blocking issues found
- [ ] Study + GP integration verified

**3. Unit tests:**
- [ ] tests/unit/test_types.py exists and passes
- [ ] tests/unit/test_gp_searcher.py exists and passes
- [ ] tests/integration/test_study_gp.py exists and passes
- [ ] Coverage >80% for new code
- [ ] pytest exits 0

**4. Code cleanup:**
- [ ] Old code namespaced or removed
- [ ] Import paths clear
- [ ] No conflicts

**5. Specification violations:**
- [ ] Old violations documented
- [ ] New code clean

**Re-Audit Verdict:**
- **PASS:** All 5 areas resolved → Proceed to Phase 1
- **PARTIAL:** Some issues remain → Document, assess if blocking
- **FAIL:** Critical issues unresolved → Continue fixes

**Deliverable:** TIER0_PHASE0_REAUDIT.md

**Quality Gates:**
- [ ] All blocking issues resolved
- [ ] Re-audit document created
- [ ] Phase marker updated to Phase 1 Day 1
- [ ] No regressions introduced

**Phase 0 Complete Criteria:**
- All 3 blocking issues fixed
- All 5 warning issues addressed or documented
- Re-audit passes
- Ready to proceed with Phase 1 (baseline implementation)

---

## Phase 1: Baseline Implementation (8 days)

### Day 1: Package/CI + Core Types [BLOCKED]

**Status:** ⚠️ INCOMPLETE - Critical issues found

**Deliverables:**
- ✅ pyproject.toml with dependencies
- ✅ requirements.txt with locked versions
- ✅ .github/workflows/ci.yml
- ✅ hponas/types.py (Config, Trial, Result, SearchSpace)
- ⚠️ hponas/searchers/gp_searcher.py (has NotImplementedError)
- ❌ Unit tests (not verified)

**Blocking Issues:**
1. GP+qLogEI incomplete
2. Tests not verified
3. Study class dependency unclear

**Next Actions:**
1. Fix GP+qLogEI implementation
2. Audit Study class
3. Write/verify unit tests
4. Re-audit before proceeding to Day 2

### Day 2: GP+qLogEI Baseline (3 days) [BLOCKED ON DAY 1]

**Authority:** BUILD_PROGRAM_v3.md lines 74-98

**LaTeX Spec:** Section 3.1 "Baseline Methods"

**Requirements:**
- Gaussian Process with Matérn 5/2 kernel (default)
- q-Expected Improvement with log transform
- L-BFGS-B acquisition optimization (10 restarts default)
- Initial random sampling: 5 trials
- Supports continuous, discrete, categorical, integer

**Preregistered Defaults:**
```python
GP_DEFAULT_KERNEL = "matern52"
GP_DEFAULT_INITIAL_RANDOM = 5
GP_DEFAULT_ACQUISITION_OPTIMIZER = "lbfgs"
GP_DEFAULT_NUM_RESTARTS = 10
```

**Implementation Plan:**
1. Fix `_prepare_training_data()` to get configs from trials
2. Implement `_config_to_tensor()` with proper categorical encoding
3. Implement `_tensor_to_config()` with proper decoding
4. Test GP on synthetic functions (Branin, Rosenbrock)
5. Verify matches BoTorch reference (for V01)

**Quality Gates:**
- [ ] All 5 Gates pass (spec, tests, integration, audit, no-regression)
- [ ] Unit tests: test_gp_posterior, test_acquisition_optimization
- [ ] Integration test: Study + GPSearcher on Branin (10 trials)
- [ ] Property test: GP predictions bounded, acquisition increases

**Validation:** V01 (vendor parity vs BoTorch)

**Duration:** 3 days (includes fixing Day 1 issues)

### Day 3-4: LocalExecutor (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 99-122

**LaTeX Spec:** Executor interface (implied from system architecture)

**Requirements:**
- Synchronous mode: blocking execution
- Asynchronous mode: non-blocking with futures
- Error handling: NaN, inf, timeout, exception
- Resource limits: CPU/memory constraints
- Checkpoint save/load

**Interface:**
```python
class LocalExecutor(BaseExecutor):
    def execute(self, trial: Trial, objective_fn: Callable) -> Result:
        """Synchronous execution."""
        
    def execute_async(self, trial: Trial, objective_fn: Callable) -> Future:
        """Asynchronous execution."""
```

**Error Handling Matrix:**
| Error Type | Status | Action |
|------------|--------|--------|
| Exception | failed | Capture traceback in metadata |
| NaN | nan | Mark as invalid, continue |
| Inf | inf | Mark as invalid, continue |
| Timeout | timeout | Kill process, mark failed |

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Unit tests: test_sync_execution, test_async_execution, test_error_handling
- [ ] Integration test: LocalExecutor + GPSearcher on simple function
- [ ] Test all error modes: exception, NaN, inf, timeout

**Validation:** tests/conformance/test_executor_contract.py

**Duration:** 1 day

### Day 5-6: RayExecutor (2 days)

**Authority:** BUILD_PROGRAM_v3.md lines 124-147

**LaTeX Spec:** Distributed execution (system architecture)

**Requirements:**
- Ray cluster management
- Fault tolerance: retry, handle worker crashes
- Resource scheduling: CPU/GPU per trial
- Parallel execution: configurable concurrency
- Progress monitoring

**Interface:**
```python
class RayExecutor(BaseExecutor):
    def __init__(self, num_workers=4, resources_per_trial=None, 
                 max_retries=3, timeout=None):
        
    def execute_batch(self, trials: List[Trial], objective_fn: Callable) -> List[Result]:
        """Parallel execution."""
```

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Unit tests: test_parallel_execution, test_fault_tolerance
- [ ] Integration test: 10 trials in parallel, verify speedup
- [ ] Test fault injection: kill worker mid-trial, verify retry

**Validation:** tests/conformance/test_executor_contract.py

**Duration:** 2 days

### Day 7: rl_routine Workload (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 149-178

**LaTeX Spec:** Section 8 "Workloads" (rl_routine)

**Requirements:**
- 9-knob search space: width, depth, activation, optimizer, lr, batch_size, dropout, weight_decay, lr_schedule
- Jax/Brax environment: Ant
- Fidelity levels: 1000, 5000, 10000 training steps
- Held-out acceptance: Humanoid (different env)

**Search Space:**
```python
{
    "width": [32, 64, 128, 256],
    "depth": [2, 3, 4],
    "activation": ["relu", "gelu", "tanh"],
    "optimizer": ["adam", "sgd"],
    "learning_rate": (1e-5, 1e-2),  # log scale
    "batch_size": [32, 64, 128],
    "dropout": (0.0, 0.3),
    "weight_decay": (1e-6, 1e-3),  # log scale
    "lr_schedule": ["constant", "cosine"]
}
```

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Unit test: test_rl_routine_search_space
- [ ] Integration test: Random search on rl_routine (10 trials)
- [ ] Verify: jax/brax dependency installed, evaluation runs
- [ ] Test fidelity levels: 1000 steps completes in <30s

**Validation:** V05 (workload correctness)

**Duration:** 1 day (includes 0.5d jax/brax install/testing)

### Day 8: Random and Sobol Baselines (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 180-193

**LaTeX Spec:** Section 3.1 "Baseline Methods"

**Requirements:**

**Random Baseline:**
- Uniform sampling from search space
- Seed-deterministic
- Handles all parameter types

**Sobol Baseline:**
- Quasi-random low-discrepancy sequence
- scipy.stats.qmc.Sobol
- Scramble=True (default)
- Better coverage than random

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Unit tests: test_random_sampling, test_sobol_coverage
- [ ] Integration test: Random vs Sobol on Branin (100 trials each)
- [ ] Property test: Sobol has lower discrepancy than random

**Validation:** V04-T0 (Sobol vs Random equivalence)

**Duration:** 1 day

---

## Remediation (17 days)

### Day 9: V01 Vendor Parity (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 214-225

**Problem:** Current V01 tautological (compares to self)

**Fix:**
- Implement BoTorch GP adapter
- Implement Optuna TPE adapter (if TPE in scope)
- V01 compares hponas.GPSearcher vs BoTorchGP
- Use equivalence test (TOST) not overlap test

**LaTeX Spec:** V01 protocol says "matches vendor implementation"

**Preregistered Protocol:**
- Tasks: Branin, Hartmann6 (held-out)
- Seeds: 42, 123, 456, 789, 1011
- Margin: 5% equivalence margin
- Alpha: 0.05 (Bonferroni corrected)
- Power: 0.8
- Analysis: TOST (two one-sided t-tests)

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v01_protocol.md (immutable)
- [ ] Vendor adapters tested independently
- [ ] V01 script runs to completion
- [ ] Results file: validation/results/v01_results.json (write-once)

**Validation:** V01 PASS required for gate

**Duration:** 1 day

### Day 10-12: V02 State Replay (3 days)

**Authority:** BUILD_PROGRAM_v3.md lines 227-238

**Problem:** No deterministic replay test

**Fix:**
- Implement get_state/set_state for all searchers
- Implement checkpoint save/load for Study
- V02 protocol: save at trial T, load, continue, verify identical

**LaTeX Spec:** Section 9 "Reproducibility"

**Preregistered Protocol:**
- Checkpoint points: trial 5, 10, 20, 50
- Seeds: 42, 123, 456, 789, 1011
- Tolerance: 0.0 (exact match)
- Analysis: Assert results[i] == replayed_results[i] for all i

**Implementation:**
```python
# Save state
state = study.get_state()  # includes searcher state, trial history
save_checkpoint(state, "checkpoint_t10.json")

# Load and replay
study2 = Study.from_checkpoint("checkpoint_t10.json")
study2.run(budget=50)  # continue from trial 10

# Verify
assert study.results == study2.results  # exact match
```

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v02_protocol.md
- [ ] Unit tests: test_state_serialization, test_checkpoint_resume
- [ ] Integration test: Resume from multiple checkpoints
- [ ] V02 script runs to completion

**Validation:** V02 PASS required for gate

**Duration:** 3 days

### Day 13-15: V03 Mutation Testing (3 days)

**Authority:** BUILD_PROGRAM_v3.md lines 240-251

**Problem:** No mutation tests exist

**Fix:**
- Configure mutmut to target hponas/searchers/, hponas/schedulers/
- Write sufficient unit tests to kill ≥90% of mutations
- Document mutations that survive with justification

**LaTeX Spec:** Section 10 "Test Quality"

**Preregistered Protocol:**
- Target: hponas/ (all core logic)
- Tool: mutmut
- Threshold: ≥0.90 mutation score
- Analysis: Review surviving mutations, add tests or justify

**Mutation Categories:**
- Arithmetic: + → -, * → /, etc.
- Comparison: < → <=, == → !=, etc.
- Constant: 0 → 1, True → False, etc.
- Statement: delete line, etc.

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v03_protocol.md
- [ ] mutmut run completes
- [ ] Mutation score ≥ 0.90
- [ ] Surviving mutations documented with justification
- [ ] V03 results file: validation/results/v03_results.json

**Validation:** V03 PASS required for gate

**Duration:** 3 days

### Day 16-17: V04-T0 Re-run (2 days)

**Authority:** BUILD_PROGRAM_v3.md lines 253-264

**Problem:** Post-hoc tuned threshold (was 10%, should be 5%)

**Fix:**
- Verify Sobol implementation correct (check against scipy.stats.qmc.Sobol)
- Preregister 5% equivalence margin
- Re-run V04-T0 with correct margin
- Use TOST not overlap test

**LaTeX Spec:** V04-T0 protocol says "5% equivalence margin"

**Preregistered Protocol:**
- Comparison: Sobol vs Random
- Task: Branin (synthetic, fast)
- Budget: 100 trials per run
- Seeds: 42, 123, 456, 789, 1011 (5 replicates)
- Margin: 5% of Random baseline mean
- Alpha: 0.05
- Power: 0.8
- Analysis: TOST

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v04_t0_protocol.md (immutable)
- [ ] Sobol implementation verified against scipy
- [ ] V04-T0 script runs to completion
- [ ] TOST used (not overlap test)
- [ ] Results file: validation/results/v04_t0_results.json

**Validation:** V04-T0 PASS required for gate

**Duration:** 2 days

### Day 18: V05 Re-run (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 266-277

**Problem:** May use toy workload instead of real rl_routine

**Fix:**
- Verify V05 uses real rl_routine with jax/brax
- 9-knob search space as specified
- ≥1000 training steps (non-trivial)

**LaTeX Spec:** V05 protocol says "real rl_routine workload"

**Preregistered Protocol:**
- Workload: rl_routine (Ant environment)
- Budget: 20 trials
- Seeds: 42, 123, 456
- Fidelity: 1000 steps
- Success criteria: All trials complete without error, objective values reasonable

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v05_protocol.md
- [ ] Real jax/brax evaluation confirmed
- [ ] V05 script runs to completion
- [ ] Results file: validation/results/v05_results.json

**Validation:** V05 PASS required for gate

**Duration:** 1 day

### Day 19: V14 Re-run (0.5 days)

**Authority:** BUILD_PROGRAM_v3.md lines 279-289

**Problem:** May have used zero-trial budgets (vacuous)

**Fix:**
- Re-run V14 with non-zero trial budgets
- Verify budget adherence check is non-trivial

**LaTeX Spec:** V14 protocol says "budget adherence with >0 trials"

**Preregistered Protocol:**
- Test: Study respects budget parameter
- Budgets: 10, 20, 50, 100
- Seeds: 42, 123
- Success criteria: Exactly budget trials executed (no more, no less)

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] Protocol file: validation/protocols/v14_protocol.md
- [ ] Non-zero budgets used
- [ ] V14 script runs to completion
- [ ] Results file: validation/results/v14_results.json

**Validation:** V14 PASS required for gate

**Duration:** 0.5 day

### Day 20-21: V16 Validator Audit (2 days)

**Authority:** BUILD_PROGRAM_v3.md lines 291-302

**Status:** COMPLETED (Week 3 Day 6 per recovery program)

**Verification Task:**
- Confirm base_validator.py implements V16 audit protocol
- Confirm all V01-V15 validators have --audit mode
- Run audit on all validators, verify pass

**V16 Audit Checks:**
1. Non-vacuity: validator fails on empty input
2. No post-hoc tuning: thresholds match protocol file
3. Correct reference: compares to vendor not self
4. Runnable independently: `python validation/vXX_*.py --audit` works

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] base_validator.py exists with audit() method
- [ ] All validators inherit from base
- [ ] `--audit` flag works for all validators
- [ ] All audits PASS

**Validation:** V16 PASS required for gate

**Duration:** 2 days (verification + fixes if needed)

### Day 22-23: Test Repair (2 days)

**Authority:** BUILD_PROGRAM_v3.md lines 304-313

**Problem:** 6 R1 tests broken (per BUILD_PROGRAM_v2.md line 155)

**Fix:**
- Identify broken tests
- Fix underlying issues (not skip/xfail)
- Ensure all tests pass in CI

**Quality Gates:**
- [ ] All 5 Gates pass
- [ ] `pytest` exits with code 0
- [ ] Coverage >80% maintained
- [ ] CI passes on main branch

**Duration:** 2 days

### Day 24: Gate Report (1 day)

**Authority:** BUILD_PROGRAM_v3.md lines 315-325

**Problem:** Previous gate report used procedural shortcuts

**Fix:**
- Honest assessment of all validations
- No "deemed PASS" without running
- Document blockers clearly
- Include V16 audit results

**Gate Report Contents:**
```markdown
# Tier 0 Gate Report

**Date:** YYYY-MM-DD
**Authority:** BUILD_PROGRAM_v3.md

## Validation Results

| Validation | Status | Evidence | Notes |
|------------|--------|----------|-------|
| V01 | PASS/FAIL | v01_results.json | ... |
| V02 | PASS/FAIL | v02_results.json | ... |
| V03 | PASS/FAIL | v03_results.json | ... |
| V04-T0 | PASS/FAIL | v04_t0_results.json | ... |
| V05 | PASS/FAIL | v05_results.json | ... |
| V14 | PASS/FAIL | v14_results.json | ... |
| V16 | PASS/FAIL | Audit logs | ... |

## Test Pyramid Status

- Layer 1: X tests, Y% coverage
- Layer 2: X tests
- Layer 3: 7 validation campaigns

## Gate Verdict

PASS / BLOCKED

If BLOCKED: specific issues listed with remediation plan.
```

**Quality Gates:**
- [ ] All validations run (not deemed)
- [ ] Honest verdict (no shortcuts)
- [ ] Artifacts referenced
- [ ] Blockers documented

**Duration:** 1 day

### Day 25: Buffer / Contingency (1 day)

**Purpose:** Handle unexpected issues, slippage, or additional fixes

**Use for:**
- Integration issues that surfaced late
- Validation failures requiring re-run
- Documentation cleanup
- Final verification before gate

**Duration:** 1 day

---

## Tier 0 Gate Criteria

**All validations must PASS (not "deemed PASS"):**

| Validation | Requirement | Evidence File |
|------------|-------------|---------------|
| ✅ V01 | Vendor Parity | validation/results/v01_results.json |
| ✅ V02 | State Replay | validation/results/v02_results.json |
| ✅ V03 | Mutation Testing ≥0.9 | validation/results/v03_results.json |
| ✅ V04-T0 | Sobol ≈ Random (5%) | validation/results/v04_t0_results.json |
| ✅ V05 | Real rl_routine | validation/results/v05_results.json |
| ✅ V14 | Budget adherence | validation/results/v14_results.json |
| ✅ V16 | Validator audit | validation/results/v16_audit_log.txt |

**Test pyramid must PASS:**
- ✅ Layer 1: >100 unit/property tests, <1s each
- ✅ Layer 2: >20 integration tests, <60s each
- ✅ Layer 3: 7 validation campaigns above

**Package requirements:**
- ✅ CI passes on main branch
- ✅ pytest exits 0
- ✅ Coverage >80%
- ✅ black, ruff, mypy pass
- ✅ No NotImplementedError in production code
- ✅ Git hash in version string

**Gate Verdict:** PASS or BLOCKED (no "deemed PASS", no "conditional")

**If BLOCKED:** Document issues, estimate remediation time, DO NOT proceed to Tier 1

---

## Risk Register

### Risk 1: Day 1 Issues Take Longer Than 3 Days to Fix

**Probability:** Medium  
**Impact:** High (delays entire Tier 0)  

**Mitigation:**
- Start fixes immediately
- Parallelize: one person fixes GP, another writes tests
- Daily standup to track progress

**Trigger:** If not fixed by Day 4, escalate for scope reduction decision

### Risk 2: Validation Campaigns Fail

**Probability:** Medium  
**Impact:** High (gate blocked)

**Mitigation:**
- Implement to specification (no shortcuts)
- Test early and often
- Run validations continuously during implementation (don't wait for Day 9+)

**Trigger:** If any validation fails, fix implementation not validation

### Risk 3: Specification Violations in Old Code

**Probability:** High (15+ documented violations)  
**Impact:** Medium (old code might be used by accident)

**Mitigation:**
- Audit old code against TRACEABILITY_MATRIX_v1.md
- Delete or namespace old code
- Clear import paths in __init__.py

**Trigger:** Day 2 - audit old code before continuing

### Risk 4: Test Writing Takes Longer Than Estimated

**Probability:** Medium  
**Impact:** Medium (delays but not blocking)

**Mitigation:**
- Write tests WHILE implementing (TDD)
- Target 80% coverage, not 100%
- Use property tests for randomized components

**Trigger:** If behind schedule, use Day 25 buffer

### Risk 5: Context Compaction Causes Drift

**Probability:** Medium  
**Impact:** High (could repeat past mistakes)

**Mitigation:**
- This master program document
- Daily phase marker updates
- Explicit recovery protocol at top of this file

**Trigger:** After each context compaction, read this file first

---

## Recovery Protocol (Post-Compaction)

If context is compacted and you resume this session:

1. **Read this file FIRST** (`TIER0_EXECUTION_MASTER_PROGRAM.md`)
2. **Check Current Phase Marker** (lines 27-35)
3. **Read LAST COMPLETED** to understand what's done
4. **Read NEXT TASK** to know what to do next
5. **Check for BLOCKED status** - don't skip blocked issues
6. **Read relevant day section** for task details
7. **Check quality gates** before executing
8. **Execute task** following gates
9. **Update phase marker** after completion
10. **Update TIER0_PROGRESS.md** with status

**NEVER:**
- Skip blocked issues
- Proceed without fixing critical issues
- Skip quality gates
- Assume work is complete without verification
- Add new features while blockers exist

---

## Daily Checklist Template

Use this checklist for each day's work:

### Planning Phase
- [ ] Read day's task description
- [ ] Identify LaTeX specification section
- [ ] Check TRACEABILITY_MATRIX_v1.md for violations
- [ ] List quality gates that apply
- [ ] Estimate effort and identify blockers

### Implementation Phase
- [ ] Write tests FIRST (TDD)
- [ ] Implement to specification
- [ ] No NotImplementedError or TODO without plan
- [ ] Document algorithm with LaTeX reference
- [ ] Run tests locally, verify pass

### Verification Phase
- [ ] Gate 1: Specification compliance ✓
- [ ] Gate 2: Test coverage >80% ✓
- [ ] Gate 3: Integration verified ✓
- [ ] Gate 4: Audit trail updated ✓
- [ ] Gate 5: No regression ✓

### Completion Phase
- [ ] Update TIER0_PROGRESS.md
- [ ] Update phase marker in this file
- [ ] Commit with descriptive message
- [ ] Push to remote (if applicable)
- [ ] Document any issues or blockers

---

## File Path Reference

### Core Program Documents
- `BUILD_PROGRAM_v3.md` - Build program authority
- `HPO_NAS_RECOVERY_MASTER_PROGRAM.md` - Recovery program (completed)
- `TIER0_EXECUTION_MASTER_PROGRAM.md` - **This file** (execution governance)
- `TIER0_PROGRESS.md` - Daily progress tracking
- `TIER0_DAY1_AUDIT.md` - Day 1 audit results

### Implementation
- `hponas/types.py` - Core types
- `hponas/searchers/gp_searcher.py` - GP+qLogEI (BLOCKED)
- `hponas/searchers/random_searcher.py` - Random baseline
- `hponas/searchers/base.py` - Searcher interface
- `hponas/executors/local_executor.py` - Local executor
- `hponas/executors/ray_executor.py` - Ray executor
- `hponas/study.py` - Study API

### Tests
- `tests/unit/` - Layer 1 tests
- `tests/conformance/` - Contract tests
- `tests/integration/` - Layer 2 tests
- `tests/property/` - Property-based tests

### Validation
- `validation/protocols/` - Preregistered protocols (immutable)
- `validation/results/` - Validation results (write-once)
- `validation/v01_*.py` through `validation/v16_*.py` - Validators

### Configuration
- `pyproject.toml` - Package config
- `requirements.txt` - Locked dependencies
- `.github/workflows/ci.yml` - CI pipeline

---

## Decision Log

### Decision 1: Stop and Audit After Day 1
**Date:** 2026-09-10  
**Decision:** Conduct thorough audit after Day 1 instead of proceeding  
**Rationale:** Found critical issues (NotImplementedError, zero tests) that could repeat RED verdict  
**Alternatives:** Proceed with risk accepted  
**Outcome:** Audit completed (TIER0_DAY1_AUDIT.md), execution blocked until fixes

### Decision 2: Mandatory Quality Gates
**Date:** 2026-09-10  
**Decision:** Establish 5 mandatory quality gates for all work  
**Rationale:** Prevent repeat of RED verdict causes (zero tests, spec violations)  
**Alternatives:** Trust implementation without verification  
**Outcome:** Gates defined in this document, mandatory for all days

### Decision 3: Create Execution Master Program
**Date:** 2026-09-10  
**Decision:** Create this governance document for Tier 0 execution  
**Rationale:** Recovery master program got us TO approval, need execution governance for THROUGH execution  
**Alternatives:** Work from BUILD_PROGRAM_v3.md directly  
**Outcome:** This document created with day-by-day plan and quality gates

---

## Success Criteria

### Day-by-Day Success
Each day is complete when:
- All 5 quality gates pass
- Tests written and passing
- Code committed with audit trail
- Phase marker updated
- No blocking issues

### Tier 0 Complete Success
Tier 0 is complete when:
- All 25 days executed
- All validations PASS (not deemed)
- Gate report shows PASS verdict
- Test pyramid complete (>100 L1, >20 L2, 7 L3)
- CI passes
- No NotImplementedError in production code
- Ready to proceed to Tier 1

### Program Success
This program succeeds if:
- Tier 0 gate PASSES with honest verdict
- Zero repeat of RED verdict causes
- Quality maintained throughout
- Context drift prevented
- All deliverables traceable to specifications

---

## Communication Protocol

### Daily Standup (If Team)
- What was completed yesterday
- What will be done today
- Any blockers

### Weekly Review
- Progress vs plan
- Validation results
- Risk assessment
- Timeline adjustment if needed

### Escalation
Escalate immediately if:
- Blocked >2 days
- Validation fails and root cause unclear
- Specification violation discovered
- Timeline slips >3 days

---

## Appendix A: Specification Violation Reference

**Source:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 83-111, TRACEABILITY_MATRIX_v1.md

**Known violations in OLD code (must not replicate):**

1. **πBO:** Uses GP mean not acquisition multiplier
   - File: `hponas/searchers_priorband.py` (old code)
   - LaTeX: Section 6.1 says acquisition multiplier
   - Fix: Delete old code or fix before use

2. **PriorBand:** Uses top-K not portfolio sampler
   - File: `hponas/searchers_priorband.py` (old code)
   - LaTeX: Section 6.2 says randomized weighted selection
   - Fix: Delete old code or fix before use

3. **ifBO:** Custom power-law not pretrained
   - File: Search for ifBO implementation
   - LaTeX: Section 6.3 says pretrained surrogate
   - Fix: Delete old code or fix before use

4. **Warm-start:** Immediate RGPE not ranked/quantile query
   - File: `hponas/warm_start.py` (old code)
   - LaTeX: Section 6.4 says query first, THEN RGPE
   - Fix: Delete old code or fix before use

**Action:** Audit old code, delete or fix, do NOT replicate violations

---

## Appendix B: Test Pyramid Reference

**Source:** TEST_PYRAMID_v1.md, BUILD_PROGRAM_v3.md Item 8

### Layer 1: Unit / Property / Conformance
- **Purpose:** Verify individual functions, contracts, invariants
- **Runtime:** <1 second per test
- **Frequency:** Every commit (CI)
- **Coverage:** >80% line coverage
- **Count target:** >100 tests

**Examples:**
- `test_config_serialization()` - roundtrip preserves value
- `test_gp_posterior()` - GP mean/variance correct on synthetic data
- `test_acquisition_maximization()` - argmax within epsilon of known optimum
- `test_searcher_contract()` - Searcher interface conformance

### Layer 2: Integration / Recovery / Scale
- **Purpose:** Verify component interactions, failure recovery, limits
- **Runtime:** <60 seconds per test
- **Frequency:** Every PR (CI)
- **Coverage:** All critical paths
- **Count target:** >20 tests

**Examples:**
- `test_study_with_gp_searcher()` - Full optimization on Branin
- `test_checkpoint_resume()` - Resume produces identical results
- `test_ray_parallel_execution()` - 10 workers, verify speedup
- `test_nan_handling()` - NaN objective handled gracefully

### Layer 3: Statistical Campaigns
- **Purpose:** Verify method effectiveness claims
- **Runtime:** Minutes to hours
- **Frequency:** Manual (gate validation)
- **Coverage:** All V01-V15 claims
- **Count:** 7 campaigns (Tier 0)

**Examples:**
- V01: Vendor parity (GP vs BoTorch)
- V02: State replay (deterministic)
- V03: Mutation testing (≥0.9 score)

---

## Appendix C: LaTeX Specification Index

**Reference:** LaTeX specification document (assumed to exist)

| Section | Title | Implementation | Status |
|---------|-------|----------------|--------|
| 3.1 | Baseline Methods | gp_searcher.py, random_searcher.py | Day 1-2, 8 |
| 4.1 | ASHA | schedulers/asha.py | Tier 1 |
| 4.2 | MO-ASHA | schedulers/mo_asha.py | Tier 1 |
| 4.3 | EI-per-cost | searchers/ei_per_cost.py | Tier 1 |
| 5.1 | qLogNEHVI | searchers/qlog_nehvi.py | Tier 1 |
| 5.2 | Chebyshev | mo_utils.py | Tier 1 |
| 5.3 | NSGA-II | searchers/nsga2.py | Tier 1 |
| 6.1 | πBO | searchers/pibo.py | Tier 1 (opt-in) |
| 6.2 | PriorBand | schedulers/priorband.py | Tier 1 (opt-in) |
| 6.3 | ifBO | searchers/ifbo.py | Tier 1 (opt-in) |
| 6.4 | Warm-start | transfer/warmstart.py | Tier 2 |
| 7.1 | TuRBO | searchers/turbo.py | Tier 2 (conditional) |
| 7.2 | BG-PBT | schedulers/bg_pbt.py | Tier 2 (conditional) |
| 8 | Workloads | workloads/rl_routine.py | Day 7 |
| 9 | Reproducibility | Study checkpoint | Day 10-12 |
| 10 | Test Quality | V03 mutation testing | Day 13-15 |

---

## Version History

**v1.0 - 2026-09-10**
- Initial execution master program
- 25-day schedule with quality gates
- Day 1 audit results incorporated
- Decision: block until critical issues fixed
- 5 mandatory quality gates established
- Recovery protocol for context compaction
- Risk register and mitigation strategies

---

## Document Status

**Status:** ACTIVE (execution blocked pending Day 1 fixes)  
**Owner:** HPO-NAS Build Program  
**Authority:** BUILD_PROGRAM_v3.md Tier 0 section  
**Version:** 1.0  
**Last Updated:** 2026-09-10  

**Current Blocker:** Day 1 critical issues (GP+qLogEI, tests, audit)

**Next Actions:**
1. User reviews audit (TIER0_DAY1_AUDIT.md)
2. User decides: fix now OR proceed with documented risks
3. If fix: implement recommendations, re-audit, update phase marker
4. If proceed: document accepted risks, update phase marker, continue Day 2

---

**END OF EXECUTION MASTER PROGRAM**
