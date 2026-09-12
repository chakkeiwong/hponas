# Contract Semantics v1

**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 2 Day 6-7  
**Purpose:** Define precise semantics for all interface contracts  
**Status:** Complete  
**Date:** 2026-09-09

---

## 1. BaseSearcher Contract

**Interface:** `hponas/searchers/base.py`

### Methods

#### `suggest() -> Config`
**Semantics:**
- **Pre-condition:** None (can be called at any time)
- **Post-condition:** Returns valid Config within search space bounds
- **Side-effects:** May update internal state (e.g., iteration counter)
- **Thread-safety:** Not guaranteed; caller must synchronize
- **Determinism:** Given same seed and observation history, produces same sequence

**Error modes:**
- Raises `ValueError` if search space is invalid or empty
- May return `None` if search exhausted (implementation-defined)

#### `observe(result: Result) -> None`
**Semantics:**
- **Pre-condition:** `result.trial_id` must correspond to a suggested config
- **Post-condition:** Result appended to history; internal model updated
- **Side-effects:** Updates history, may trigger model retraining
- **Idempotency:** Multiple observations of same trial_id are allowed; last wins
- **NaN/Inf handling:** Invalid results (NaN/inf) added to history but excluded from model training

**Error modes:**
- Does not raise on NaN/inf objective values
- May raise if trial_id is unknown (implementation-defined)

#### `get_state() -> Dict[str, Any]`
**Semantics:**
- **Pre-condition:** None
- **Post-condition:** Returns JSON-serializable dict capturing complete state
- **Side-effects:** None (read-only)
- **Completeness:** Must include history, RNG state, hyperparameters

**Error modes:**
- Must not raise (returns empty dict on error)

#### `set_state(state: Dict[str, Any]) -> None`
**Semantics:**
- **Pre-condition:** `state` must be from prior `get_state()` call
- **Post-condition:** Searcher restored to exact state, next suggest() is deterministic
- **Side-effects:** Replaces entire internal state
- **Backward-compatibility:** Must handle states from same major version

**Error modes:**
- Raises `ValueError` if state is invalid or incompatible
- Raises `KeyError` if required keys are missing

---

## 2. BaseScheduler Contract (ASHA)

**Interface:** `hponas/schedulers.py` (pending refactor)

### Methods

#### `suggest() -> (Config, float)`
**Semantics:**
- **Pre-condition:** None
- **Post-condition:** Returns (config, fidelity) pair
- **Fidelity assignment:** 
  - New trials start at `min_fidelity`
  - Promoted trials receive next rung fidelity
  - Never exceeds `max_fidelity`
- **Side-effects:** Updates bracket state, may spawn new bracket

**Error modes:**
- Returns `(None, 0.0)` if all brackets exhausted

#### `observe(result: Result) -> None`
**Semantics:**
- **Pre-condition:** `result.fidelity` matches assigned fidelity
- **Post-condition:** Rung updated, promotion decisions made
- **Promotion rule:** Top `1/eta` fraction promoted to next rung
- **Side-effects:** May trigger rung promotions, bracket completion
- **Early stopping:** Trials not in top `1/eta` are stopped

**Error modes:**
- Raises `ValueError` if fidelity mismatch
- Handles NaN by treating as worst performance (not promoted)

#### `get_state() -> Dict[str, Any]`
**Semantics:**
- **Pre-condition:** None
- **Post-condition:** Returns bracket state, rung populations, promotion queues
- **Completeness:** Must include all rungs, all pending promotions

#### `set_state(state: Dict[str, Any]) -> None`
**Semantics:**
- **Pre-condition:** Valid ASHA state dict
- **Post-condition:** All brackets restored, promotion queue intact
- **Resume behavior:** Next suggest() continues from last bracket

---

## 3. BaseExecutor Contract

**Interface:** `hponas/executors/base.py`

### Methods

#### `execute(trial: Trial, objective_fn: Callable) -> Result`
**Semantics:**
- **Pre-condition:** Trial has valid config and fidelity
- **Post-condition:** Returns Result with status
- **Execution:** Calls `objective_fn(trial.config.values)`
- **Timeout:** Respects `self.timeout` if set (implementation-defined)
- **Side-effects:** None to searcher/scheduler state

**Error modes:**
- Returns `Result(status="failed")` on exception
- Returns `Result(status="nan")` on NaN objective
- Returns `Result(status="inf")` on inf objective
- Returns `Result(status="timeout")` on timeout
- Never propagates exceptions to caller

#### `execute_async(trial: Trial, objective_fn: Callable) -> Future`
**Semantics:**
- **Pre-condition:** Executor in async mode
- **Post-condition:** Returns Future, work submitted to thread pool
- **Concurrency:** Respects `max_workers` limit
- **Future resolution:** Future.result() returns Result
- **Blocking:** Future blocks until completion or timeout

**Error modes:**
- Raises `ValueError` if not in async mode
- Future propagates no exceptions; errors encoded in Result.status

#### `shutdown() -> None`
**Semantics:**
- **Pre-condition:** None
- **Post-condition:** All workers stopped, resources released
- **Blocking:** Waits for pending work to complete
- **Idempotency:** Safe to call multiple times

---

## 4. Store Contract (Pending Implementation)

**Interface:** TBD (`hponas/store.py` needs refactor)

### Crash-Safe Writes

**Atomic write pattern:**
```python
# Correct pattern (no partial writes visible)
write_to_temp_file(data)
fsync(temp_file)
atomic_rename(temp_file, target_file)
fsync(parent_dir)
```

**Semantics:**
- **Atomicity:** Either old or new state visible, never partial
- **Durability:** Survives kill -9 during write
- **Consistency:** Checksum verified on load

**Error modes:**
- Returns `None` on corrupted state (checksum mismatch)
- Falls back to `.bak` file if main file corrupted
- Raises `IOError` if both main and backup corrupted

### Concurrent Writes

**Semantics:**
- **Isolation:** File-level locking (flock or equivalent)
- **Last-writer-wins:** No merge semantics
- **Deadlock-free:** Timeout on lock acquisition (5s default)

---

## 5. SearchSpace Contract

**Interface:** `hponas/types.py::SearchSpace`

### Methods

#### `sample_random(seed: Optional[int]) -> Config`
**Semantics:**
- **Pre-condition:** Space is non-empty
- **Post-condition:** Returns Config with all parameters sampled
- **Distribution:**
  - Continuous: uniform in bounds (or log-uniform if `log_scale=True`)
  - Integer: uniform in [low, high] inclusive
  - Categorical/Discrete: uniform over choices
- **Determinism:** Same seed produces same config

**Error modes:**
- Raises `ValueError` if space is empty
- Raises `ValueError` if bounds are invalid (low > high)

#### `validate_config(config: Config) -> bool`
**Semantics:**
- **Pre-condition:** Config has dict of parameter values
- **Post-condition:** Returns True if all parameters in bounds/choices
- **Checks:**
  - All required parameters present
  - Continuous/integer values in bounds
  - Categorical/discrete values in choices
  - No extra parameters

---

## 6. Mutation Testing Targets

**Goal:** Mutation score ≥ 0.9 for Week 3 V03 validation

### High-Value Mutations to Kill

1. **Off-by-one errors:**
   - `range(n)` → `range(n+1)`
   - `<` → `<=`
   - `low, high+1` → `low, high`

2. **Comparison operator flips:**
   - `>` → `<`
   - `>=` → `>`
   - `==` → `!=`

3. **Constant changes:**
   - `initial_random_samples = 5` → `= 4`
   - `eta = 3` → `= 2`
   - `quantile = 1/eta` → `= 1/(eta-1)`

4. **Missing checks:**
   - Remove `if not np.isfinite(...)`
   - Remove `if result.is_valid()`
   - Remove `if state is None`

5. **State corruption:**
   - Remove field from `get_state()`
   - Skip field in `set_state()`
   - Forget to restore RNG state

### Test Coverage Requirements

- All contract tests must pass
- Each mutation target has ≥1 test that fails when mutated
- Critical paths (suggest/observe/checkpoint) have ≥90% branch coverage

---

## 7. Version Compatibility

**State serialization:**
- Major version changes may break compatibility
- Minor version changes must be backward-compatible
- Patch version changes must be fully compatible

**Upgrade path:**
- v1.x → v1.y: load old checkpoints directly
- v1.x → v2.0: migration script required

**Deprecation policy:**
- Deprecated APIs supported for one major version
- Warnings emitted for 6 months before removal

---

## 8. Open Questions (to be resolved in W2.7)

1. ~~Should `suggest()` return `None` or raise when search exhausted?~~  
   **Resolution:** Return None; caller checks and handles

2. ~~Should `observe()` raise on unknown trial_id?~~  
   **Resolution:** No raise; silently ignore (robust to duplicate/late observations)

3. ~~Store concurrent write strategy: lock file or lock-free?~~  
   **Resolution:** File-level locking (flock) with timeout

4. ~~ASHA rung promotion: strict top-k or probabilistic?~~  
   **Resolution:** Strict top-k by objective value

5. ~~Checkpoint backward compatibility guarantee?~~  
   **Resolution:** Within same major version only

---

## 9. References

- LaTeX Spec: `reconstruction/hpo_nas_paper.tex` Section 3.1
- Traceability: `TRACEABILITY_MATRIX_v1.md`
- Test Suite: `tests/conformance/test_*_contract.py`
- Build Program: `BUILD_PROGRAM_v3.md` Item 8

---

**Sign-off:** Week 2 Day 6-7 Complete  
**Next:** Week 3 Validation (V01-V15)
