# Missing Contract Semantics

**Status:** Week 2 Day 3-4 deliverable (W2.6)  
**Authority:** BUILD_PROGRAM_REVIEW_VERDICT.md lines 36, 220, 231-251  
**Task:** Define missing semantics that block Phase 0 contract freeze  
**Created:** 2026-09-09  

---

## Context

BUILD_PROGRAM_REVIEW_VERDICT.md lines 36: "Phase 0 contracts unfrozen - missing semantics for schema migration, event ordering, NaN handling, failure policy, checkpoint format"

Survey 15-contracts.tex lines 270-281: Contracts are falsified by construction work. If tier 0 implementations cannot be expressed behind these interfaces without holes, the contracts change before code doubles down. Interfaces are the product's most expensive thing to change later.

This document identifies missing semantics that prevent Phase 0 contract freeze and defines resolution paths.

---

## 1. Schema Migration

**Missing semantics:**
- No versioning in state_dict() / load_state_dict()
- No forward/backward compatibility policy
- No migration path when contract changes
- No schema validation on load

**Impact:**
- Cannot upgrade searcher/scheduler implementations safely
- Cannot support study migration across package versions
- Crash recovery fails when versions mismatch
- No way to detect incompatible state

**Required semantics:**

### 1.1 State dict versioning
```python
def state_dict(self) -> dict[str, Any]:
    """Returns serializable state with version metadata."""
    return {
        "__version__": "1.0",  # Semantic version
        "__schema__": "RandomSearcher",  # Implementation identifier
        "state": {...}  # Actual state
    }
```

### 1.2 Version compatibility check
```python
def load_state_dict(self, state: dict[str, Any]) -> None:
    """Load state with version validation and migration."""
    version = state.get("__version__", "0.0")
    schema = state.get("__schema__", "unknown")
    
    if schema != self.__class__.__name__:
        raise ValueError(f"Schema mismatch: {schema} != {self.__class__.__name__}")
    
    if version != CURRENT_VERSION:
        state = self._migrate(state, from_version=version)
    
    self._restore(state["state"])
```

### 1.3 Migration protocol
- Each searcher/scheduler implements `_migrate(state, from_version) -> dict`
- Migration paths: 0.0→1.0, 1.0→1.1, etc. (forward only)
- Backward compatibility: refuse to load future versions
- Test requirement: roundtrip state_dict/load_state_dict at current version
- Test requirement: load fixture states from all supported prior versions

**Resolution:** Add version fields to W2.1-W2.5 contract tests, create migration test suite.

---

## 2. Event Ordering

**Missing semantics:**
- No guarantee that observe() sees trials in submission order
- No specification for concurrent observe() calls
- Scheduler report() ordering undefined with async trials
- promote() timing relative to observe() unclear

**Impact:**
- Race conditions in ASHA rung bookkeeping
- Non-deterministic replay after crash
- Searcher model updates may use stale data
- Cannot prove correctness under distributed execution

**Required semantics:**

### 2.1 Observation order guarantee
```python
# Option A: Sequential consistency (strong, expensive)
# Searcher sees trials in global submission order
# Requires coordinator serialization

# Option B: Per-trial consistency (weak, practical)
# Each trial's results observed in fidelity order
# No cross-trial ordering guarantee
# Searcher must handle arbitrary interleaving
```

**Recommendation:** Option B (per-trial consistency)
- Survey assumes async trials (Ch 5, 11)
- Searcher models (GP, TPE) are permutation-invariant over observations
- ASHA only needs per-trial fidelity ordering for rung promotion
- Avoids coordinator bottleneck

**Contract addition:**
```python
def observe(self, trial: dict[str, Any]) -> None:
    """
    Ingest completed trial result.
    
    Ordering guarantee: Results for a single trial_id arrive in
    fidelity order. No ordering guarantee across different trial_ids.
    Searcher must be robust to arbitrary interleaving.
    """
```

### 2.2 Scheduler event sequence
```python
# Event types in arrival order:
# 1. report(trial_id, fidelity, value) - partial result
# 2. promote() - scheduler decides which trials to continue
# 3. executor.launch() - promoted trials resume
# 4. report(trial_id, higher_fidelity, value) - next rung

# Missing: happens-before relation between report() and promote()
```

**Required semantics:**
- `promote()` sees all `report()` calls up to invocation time
- `promote()` may be called at any time (coordinator-driven)
- `promote()` returns snapshot at call time, subsequent reports don't retroactively change past promotion
- Multiple `promote()` calls are idempotent if no new reports arrived

**Contract addition:**
```python
def promote(self) -> list[str]:
    """
    Return trial_ids eligible for continuation.
    
    Snapshot semantics: returns decisions based on all report() calls
    before this invocation. Idempotent if no new reports since last call.
    """
```

### 2.3 Event replay determinism
BUILD_PROGRAM_REVIEW_VERDICT.md lines 233-235: "Give every report and scheduler decision a stable event ID and monotonic per-trial sequence. Persist searcher and scheduler snapshots with version and last applied event ID, then prove deterministic replay after coordinator restart."

**Required for crash recovery:**
- Event log with monotonic IDs
- Checkpoint includes last-applied event ID
- Replay from checkpoint skips already-applied events
- Deterministic output given same event sequence

**Test requirement:** Crash-and-resume test in W3 validation repair

**Resolution:** Add event ordering specs to contract docstrings, create determinism test.

---

## 3. NaN Handling

**Missing semantics:**
- What does observe(trial) do if value is NaN?
- What does scheduler.report() return for NaN?
- How do NaN trials affect searcher model fitting?
- Are NaN and infinity treated identically?

**Impact:**
- Undefined behavior when objective crashes
- GP/TPE may fail to fit with NaN observations
- ASHA rung comparisons break with NaN
- Inconsistent treatment across implementations

**Required semantics:**

### 3.1 Observation contract
```python
# Option A: Reject NaN at contract boundary
def observe(self, trial: dict[str, Any]) -> None:
    if not math.isfinite(trial["value"]):
        raise ValueError("NaN/inf values must be handled before observe()")

# Option B: Accept NaN, treat as "no information"
def observe(self, trial: dict[str, Any]) -> None:
    """
    NaN/inf values are recorded but excluded from model fitting.
    Searcher tracks failure rate but does not use for prediction.
    """

# Option C: Accept NaN, convert to worst-seen
def observe(self, trial: dict[str, Any]) -> None:
    """
    NaN/inf converted to worst_seen_value - margin for minimization,
    or best_seen_value + margin for maximization.
    """
```

**Recommendation:** Option B (accept NaN, treat as no information)
- Most robust to implementation bugs
- Allows searcher to track failure modes
- Aligns with survey's "trial status" concept (Ch 15:199-201)
- GP/TPE can exclude from training data

**Contract addition:**
```python
class Trial:
    """
    Trial result with status tracking.
    
    value: float | None - objective value, None if failed
    status: Literal["completed", "failed", "stopped", "pending"]
    """
    trial_id: str
    config: dict[str, Any]
    value: Optional[float]  # None or NaN for failed trials
    status: str
    
def observe(self, trial: Trial) -> None:
    """
    Ingest trial result. Failed trials (value=None or NaN) are
    recorded but excluded from model fitting. Searcher may use
    failure rate for acquisition adjustment.
    """
```

### 3.2 Scheduler NaN handling
```python
def report(self, trial_id: str, fidelity: float, value: float) -> SchedulerDecision:
    """
    What does ASHA do with NaN at a rung?
    
    Option A: Treat as worst-performing, stop immediately
    Option B: Exclude from rung ranking, continue by default
    Option C: Configurable policy (stop/continue/pause)
    """
```

**Recommendation:** Option A (treat as worst, stop)
- Failed trials shouldn't consume higher fidelity budget
- Aligns with ASHA's "stop bad performers" goal
- Clear, predictable behavior

**Contract addition:**
```python
def report(self, trial_id: str, fidelity: float, value: float) -> SchedulerDecision:
    """
    Stream partial result, return continuation decision.
    
    NaN/inf values are treated as worst-performing and trigger 'stop'.
    """
```

**Resolution:** Add NaN test cases to W2.1-W2.5 tests, update Trial schema.

---

## 4. Failure Policy

**Missing semantics:**
- What happens when executor.launch() crashes?
- What happens when objective_fn raises exception?
- Retry policy undefined
- Resource cleanup after failure unclear
- Trial vs study-level failure distinction missing

**Impact:**
- No fault tolerance
- Resource leaks on crash
- Unclear when to abandon trial vs whole study
- Executor implementations inconsistent

**Required semantics:**

### 4.1 Trial-level failure
```python
class Executor(Protocol):
    def launch(
        self,
        trial_id: str,
        config: dict,
        objective_fn: Callable,
        fidelity: float
    ) -> str:
        """
        Launch trial, return trial_id.
        
        Failure modes:
        - ResourceError: No workers/GPUs available (transient)
        - ConfigError: Invalid config (permanent)
        - ObjectiveError: objective_fn crashed (permanent for this config)
        
        Executor catches ObjectiveError, writes Trial(status="failed"),
        returns normally. Coordinator sees failed trial in next poll.
        
        ResourceError propagates to coordinator, triggers backoff/retry.
        """
```

**Retry policy:**
- ResourceError: Retry with exponential backoff (3 attempts)
- ObjectiveError: Mark trial failed, don't retry
- ConfigError: Mark trial failed, log warning
- Checkpoint corruption: Fail trial, mark checkpoint invalid

### 4.2 Checkpoint failure
```python
def checkpoint(self, trial_id: str, path: Path) -> None:
    """
    Save trial state for crash recovery.
    
    Failure modes:
    - IOError (disk full): Propagate to coordinator, pause study
    - PickleError (unserializable state): Log error, continue without checkpoint
    - CorruptCheckpoint on load: Fail trial, restart from scratch
    """
```

### 4.3 Study-level failure
```python
# Conditions that stop entire study:
# - Store unavailable (SQLite locked, Postgres down)
# - Coordinator crash (restart from last checkpoint)
# - Budget exhausted
# - User cancellation

# Conditions that don't stop study:
# - Individual trial failures
# - Transient resource errors
# - Checkpoint save errors (log + continue)
```

**Contract test requirements:**
- Test objective_fn raising exception
- Test disk full during checkpoint
- Test corrupt checkpoint load
- Test resource exhaustion

**Resolution:** Add failure mode tests to W3.3 (V03 repair), update Executor contract.

---

## 5. Checkpoint Format

**Missing semantics:**
- What exactly is in a checkpoint?
- Pickle format? JSON? Custom binary?
- Compatibility across Python versions?
- Checkpoint validation on load?
- Checkpoint versioning?

**Impact:**
- Cannot guarantee crash recovery works
- Checkpoint surgery (population line) undefined
- No checkpoint migration path
- Security risk (pickle arbitrary code execution)

**Required semantics:**

### 5.1 Checkpoint contents
```python
# Executor checkpoint (per trial):
{
    "trial_id": str,
    "config": dict,
    "fidelity": float,
    "state": bytes,  # Pickled model/optimizer state
    "rng_state": dict,  # NumPy/PyTorch RNG state
    "metrics": list[dict],  # History of reported values
    "timestamp": str,  # ISO 8601
    "version": str,  # Package version
}

# Searcher checkpoint (per study):
{
    "searcher_class": str,
    "version": str,
    "observed_trials": list[Trial],
    "pending_trials": list[dict],  # Proposed but not yet observed
    "model_state": dict,  # GP hyperparams, TPE KDE state, etc.
    "rng_state": dict,
}

# Scheduler checkpoint (per study):
{
    "scheduler_class": str,
    "version": str,
    "rungs": dict[float, list[str]],  # fidelity → trial_ids
    "stopped_trials": set[str],
    "promoted_trials": set[str],
}
```

### 5.2 Serialization format
**Recommendation:** Pickle for model state (standard, Python-native), JSON for metadata

**Security:** Checkpoint loading must trust checkpoint source. Don't load untrusted checkpoints.

**Compatibility:** 
- Python 3.11+ only (match survey)
- PyTorch 2.0+ (checkpoint format stability)
- Refuse to load checkpoint from different major version

### 5.3 Checkpoint validation
```python
def load_checkpoint(self, trial_id: str, path: Path) -> Any:
    """
    Load trial checkpoint with validation.
    
    Validates:
    - File exists and readable
    - Pickle can be deserialized
    - Version compatible
    - trial_id matches
    - Schema valid
    
    Raises CheckpointError on any validation failure.
    """
```

### 5.4 Checkpoint surgery (population line)
Survey 15-contracts.tex lines 232-234: "checkpoint surgery (Chapter~\ref{sec:population}) is the trial-level scalpel: promote trial A by hot-replacing its weight checkpoint with trial B's, then resume. The contract: both must be picklable."

**Required semantics:**
- Checkpoints must be interchangeable for compatible architectures
- `executor.load_checkpoint()` must accept checkpoint from different trial
- Incompatible architecture checkpoints must fail gracefully
- Test requirement: Cross-trial checkpoint loading

**Resolution:** Add checkpoint schema to Executor contract, create validation tests.

---

## 6. Multi-Objective Semantics

**Missing semantics:**
- Trial.value is float, but MO needs vector
- Scheduler.report() takes single value, not vector
- Capabilities doesn't declare MO support
- Pareto front output format undefined

**Impact:**
- MO-ASHA unimplementable with current contracts
- EHVI searcher can't return vector observations
- No way to query Pareto front from store

**Required semantics:**

### 6.1 Trial schema extension
```python
class Trial:
    trial_id: str
    config: dict[str, Any]
    value: Optional[float | list[float]]  # Scalar or vector
    objectives: Optional[list[str]]  # ["latency", "memory"]
    status: str
```

### 6.2 Scheduler MO extension
```python
def report(
    self,
    trial_id: str,
    fidelity: float,
    value: float | list[float]  # Vector for MO
) -> SchedulerDecision:
    """
    For MO: value is vector, rung ranking uses dominance + crowding.
    """
```

### 6.3 Store Pareto query
```python
def pareto_front(self, study_id: str) -> list[Trial]:
    """Return non-dominated trials (MO studies only)."""
```

**Resolution:** Defer to Tier 1 (W3.5, W3.6). Add MO flag to capabilities for now.

---

## 7. Seed Split Semantics

**Missing semantics:**
- How are seeds split between optimizer and training?
- Who owns RNG state?
- Reproducibility guarantee undefined

**Impact:**
- Cannot guarantee deterministic replay
- Test seeds may leak to searcher
- Different executors produce different results with same config

**Required semantics:**

### 7.1 Seed hierarchy
BUILD_PROGRAM_REVIEW_VERDICT.md lines 245-247: "optimizer seed, training seeds, test-seed policy. Retry must not accidentally reuse or change a logical seed. Protected test seeds must be inaccessible to searcher/scheduler code until selection is frozen."

```python
# Three seed levels:
# 1. Study seed (from StudySpec) → searcher RNG
# 2. Trial seed (from searcher.propose()) → training RNG
# 3. Test seed (held by executor) → evaluation RNG

class SearchSpace:
    study_seed: int  # Searcher uses this
    
def propose(self, n: int) -> list[dict[str, Any]]:
    """
    Each config includes trial_seed drawn from study RNG.
    Searcher MUST NOT see test seeds.
    """
    configs = []
    for _ in range(n):
        config = self._sample_config()
        config["trial_seed"] = self._rng.integers(0, 2**31)
        configs.append(config)
    return configs

def launch(self, trial_id: str, config: dict, objective_fn: Callable, fidelity: float) -> str:
    """
    Executor splits trial_seed:
    - Training seed: from config["trial_seed"]
    - Test seed: from executor's protected RNG (never revealed to searcher)
    """
    training_seed = config["trial_seed"]
    test_seed = self._test_rng.integers(0, 2**31)  # Protected
    return objective_fn(config, training_seed, test_seed, fidelity)
```

**Resolution:** Add seed tests to W2.1 (Searcher contract), document in contracts.

---

## 8. Budget Arithmetic

**Missing semantics:**
- Budget units undefined (trials? cost? time?)
- Partial trial cost accounting unclear
- Checkpoint cost not tracked
- Fidelity-to-cost mapping missing

**Impact:**
- Cannot enforce study budget
- Cost-aware acquisition broken
- Fair comparison across methods impossible

**Required semantics:**

### 8.1 Budget model
BUILD_PROGRAM_REVIEW_VERDICT.md lines 241-243: "Enforce hard study and trial budgets from measured usage. RL fidelity should be environment steps or another workload resource, not blindly training_iteration."

```python
class StudySpec:
    max_trials: int  # Hard limit on trial count
    max_cost: float  # Hard limit on aggregate cost
    max_walltime: float  # Hard limit on study duration (seconds)
    
class Trial:
    cost: float  # Measured cost (GPU-hours, steps, etc.)
    walltime: float  # Actual elapsed time
    
# Coordinator checks budget before propose():
if study.total_cost + estimated_cost > study.max_cost:
    stop_study()
```

### 8.2 Fidelity-to-cost conversion
```python
def fidelity_to_cost(fidelity: float, config: dict) -> float:
    """
    Convert fidelity (0-1 or step count) to resource cost.
    
    For RL: cost = num_environment_steps * step_cost(config)
    For vision: cost = num_epochs * batch_size / throughput(config)
    """
```

**Resolution:** Add cost tracking to Trial schema, defer full implementation to Tier 0.

---

## Summary Table

| Semantic Gap | Impact | Resolution Path | Week |
|---|---|---|---|
| Schema migration | Cannot upgrade safely | Add version fields, migration tests | W2 (this doc) |
| Event ordering | Non-deterministic replay | Specify per-trial consistency | W2 (this doc) |
| NaN handling | Undefined crashes | Treat as no-info, stop in ASHA | W2 (this doc) |
| Failure policy | No fault tolerance | Define retry policy, failure modes | W3.3 (V03 repair) |
| Checkpoint format | Unreliable recovery | Specify schema, validation | W3.4 (V04-T0 repair) |
| Multi-objective | MO-ASHA unimplementable | Extend Trial/report to vectors | Defer to Tier 1 |
| Seed split | Non-reproducible | Three-level hierarchy | W2.1 tests |
| Budget arithmetic | Cannot enforce limits | Add cost tracking | Defer to Tier 0 |

**Contract freeze blockers (must resolve before Phase 0 freeze):**
1. Schema migration (W2)
2. Event ordering (W2)
3. NaN handling (W2)
4. Failure policy (W3)
5. Checkpoint format (W3)

**Defer to later tiers:**
- Multi-objective (Tier 1)
- Budget arithmetic (Tier 0 implementation)

---

## Next Steps

1. Update W2.1-W2.5 contract tests to include:
   - Version fields in state_dict()
   - NaN handling test cases
   - Event ordering docstrings
   - Seed split validation

2. Create dedicated test files:
   - `tests/test_schema_migration.py` (version roundtrip)
   - `tests/test_nan_handling.py` (failure modes)
   - `tests/test_seed_split.py` (reproducibility)

3. Update contract docstrings in:
   - `hponas/searchers.py` (Searcher Protocol)
   - `hponas/schedulers.py` (Scheduler Protocol)
   - `hponas/executors.py` (Executor Protocol)
   - `hponas/store.py` (Store methods)

4. W3 validation repair incorporates failure and checkpoint semantics.

**Status:** Ready for review and incorporation into W3 validation repair work.
