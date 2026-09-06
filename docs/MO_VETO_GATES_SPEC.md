# MO Veto Gates Implementation Spec

**Date:** 2026-09-07  
**Effort:** ~1.5 engineer-days  
**Context:** BUILD_PROGRAM_v2.md Tier 1 Tests (~7d), item "MO veto logic tests"

---

## What Are Veto Gates?

From hpo-survey/sections/15-contracts.tex line 152:

> `gate(predicate)`: Register a veto evaluated at every rung. A trial failing its gate is discarded regardless of its score; this is the sampler workload's divergence and split-R̂ machinery generalized into a hook (Chapter 9 workloads), and MO-ASHA's correctness gates use the same mechanism (Chapter 7 MO).

**Purpose:** Ensure MO-ASHA can enforce correctness constraints (e.g., constraint violations, numerical instability, invalid configurations) that must hold regardless of objective quality.

**Key property:** A veto-failing trial is **never promoted**, even if it dominates the Pareto front.

---

## Requirements

### Functional

1. **`gate(predicate)` API**
   - `MOASHAScheduler.gate(predicate: Callable[[str, dict], bool])` registers a veto
   - Multiple gates can be registered (logical AND: trial must pass all)
   - Predicate signature: `predicate(trial_id: str, objectives: dict[str, float]) -> bool`
   - Returns `True` if trial passes, `False` if trial should be vetoed

2. **Veto evaluation timing**
   - Gates are evaluated at every rung when `report()` is called
   - A failing gate immediately marks the trial as vetoed
   - Vetoed trials return "stop" from `report()`, not "pause"

3. **Promotion exclusion**
   - `promote()` never includes vetoed trials in the candidate pool
   - Vetoed trials are removed before Pareto ranking and hypervolume computation
   - Veto status persists across rungs (once vetoed, always vetoed)

4. **Tracking**
   - `_trial_state` includes veto status: `(rung_idx, fidelity, objectives, status, vetoed: bool)`
   - `get_vetoed_trials() -> list[str]` returns trial IDs that failed any gate
   - `get_veto_reasons(trial_id: str) -> list[str]` returns which gates failed (optional for Tier 1)

### Non-functional

5. **Zero performance cost when unused**
   - Empty gate list → no per-rung overhead beyond the list check

6. **Idempotent**
   - Calling `gate()` multiple times with the same predicate is safe (no duplicate checks)

7. **Validation-ready**
   - V13 will test that veto-failing configs are never promoted
   - V10 may use gates to enforce constraint satisfaction on MO tasks

---

## API Design

### Registration

```python
scheduler = MOASHAScheduler(config)

# Example: veto trials with NaN objectives
def no_nan_gate(trial_id: str, objectives: dict[str, float]) -> bool:
    return all(not np.isnan(v) for v in objectives.values())

scheduler.gate(no_nan_gate)

# Example: veto trials violating a constraint
def constraint_gate(trial_id: str, objectives: dict[str, float]) -> bool:
    # Hypothetical: latency must be < 100ms
    return objectives.get("latency", 0.0) < 100.0

scheduler.gate(constraint_gate)
```

### Usage (unchanged for users)

```python
decision = scheduler.report("trial_0", fidelity=1.0, objectives={"loss": 0.5, "latency": 45.0})
# decision is "stop" if any gate fails, "pause" if all pass and at rung, "continue" otherwise

promotions = scheduler.promote()
# vetoed trials excluded from candidate pool
```

### Inspection

```python
vetoed = scheduler.get_vetoed_trials()
# ["trial_0", "trial_5"] if those failed gates

# Optional (defer to Tier 2 if time-constrained):
reasons = scheduler.get_veto_reasons("trial_0")
# ["no_nan_gate", "constraint_gate"]
```

---

## Implementation Plan

### 1. Add gate storage to `MOASHAScheduler.__init__` (0.1d)

```python
self._gates: list[Callable[[str, dict[str, float]], bool]] = []
self._vetoed_trials: set[str] = set()
```

### 2. Implement `gate()` method (0.1d)

```python
def gate(self, predicate: Callable[[str, dict[str, float]], bool]) -> None:
    """Register a veto evaluated at every rung."""
    self._gates.append(predicate)
```

### 3. Update `_trial_state` schema (0.1d)

Change from:
```python
self._trial_state: dict[str, tuple[int, float, np.ndarray, str]] = {}
# (rung_idx, fidelity, objectives, status)
```

To:
```python
self._trial_state: dict[str, tuple[int, float, np.ndarray, str, bool]] = {}
# (rung_idx, fidelity, objectives, status, vetoed)
```

Update all reads/writes throughout the class.

### 4. Evaluate gates in `report()` (0.2d)

After extracting `obj_values`, before updating state:

```python
# Check veto gates
if self._gates:
    objectives_dict = {name: val for name, val in zip(self.config.objectives, obj_values)}
    for gate_fn in self._gates:
        if not gate_fn(trial_id, objectives_dict):
            # Veto this trial
            self._vetoed_trials.add(trial_id)
            self._trial_state[trial_id] = (rung_idx, fidelity, obj_values, "vetoed", True)
            return "stop"
```

### 5. Exclude vetoed trials in `promote()` (0.1d)

Before ranking:

```python
# Filter out vetoed trials
pop = [(tid, obj) for tid, obj in self._rung_populations[rung_idx] if tid not in self._vetoed_trials]
```

### 6. Add inspection methods (0.1d)

```python
def get_vetoed_trials(self) -> list[str]:
    """Return trial IDs that failed any gate."""
    return sorted(self._vetoed_trials)
```

### 7. Write tests (0.8d)

**Test coverage:**

- `test_mo_asha_gate_registration`: register gates, verify stored
- `test_mo_asha_gate_veto_stops_trial`: failing gate → "stop" from `report()`
- `test_mo_asha_vetoed_trial_not_promoted`: vetoed trial excluded from `promote()`
- `test_mo_asha_gate_passes_normal_flow`: passing gate → normal ASHA flow
- `test_mo_asha_multiple_gates_all_must_pass`: AND logic across gates
- `test_mo_asha_veto_persists_across_rungs`: once vetoed, never un-vetoed
- `test_mo_asha_vetoed_trial_excluded_from_pareto`: vetoed trial not in Pareto ranking
- `test_mo_asha_no_gates_zero_overhead`: empty gate list → normal behavior

**Edge cases:**

- Veto at first rung vs intermediate rung vs final rung
- Veto a Pareto-optimal trial (should still be excluded)
- All trials vetoed (promote returns empty list)

---

## Validation Tie-In

**V13 (sampler veto correctness):** Uses the same `gate()` API for MCMC diagnostics:
- Divergences → veto
- R̂ > 1.01 → veto
- ESS < 400 → veto

V13's pass rule: "no veto-failing configs promoted"

**V10 (MO rung correlation):** May use gates to enforce constraints on cheap fidelity signals before allowing MO-ASHA to kill on them.

---

## Success Criteria

1. All 8+ tests passing
2. Zero behavior change when no gates registered (existing tests still pass)
3. `get_vetoed_trials()` callable from validation harnesses
4. Documentation updated in `hponas/schedulers.py` docstring

---

## Out of Scope (Tier 1)

- Named gates (tracking which specific gate failed) — defer to Tier 2 if needed for V13 diagnosis
- Gate evaluation on non-rung fidelities — survey says "at every rung", intermediate fidelities continue
- Soft vetoes (warnings vs hard stops) — Tier 1 is binary pass/fail
- Gate state serialization (checkpoint/resume) — defer until population methods need it

---

## Estimated Effort Breakdown

| Task | Effort |
|------|--------|
| Schema changes (`_trial_state`, `_gates`, `_vetoed_trials`) | 0.2d |
| `gate()` method + gate evaluation in `report()` | 0.3d |
| Exclude vetoed trials in `promote()` | 0.1d |
| Inspection methods | 0.1d |
| Test suite (8 tests) | 0.8d |
| **Total** | **1.5d** |

---

## Next Steps

1. Read existing `MOASHAScheduler` implementation end-to-end
2. Implement schema changes and `gate()` method
3. Update `report()` to evaluate gates and veto
4. Update `promote()` to exclude vetoed trials
5. Write test suite
6. Run full scheduler test suite to verify no regressions
7. Update `docs/TIER1_PROGRESS_SUMMARY.md` with completion
