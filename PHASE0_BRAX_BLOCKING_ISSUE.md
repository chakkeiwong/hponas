# Phase 0: Brax API Blocking Issue

**Status:** BLOCKED - Requires environment fix  
**Date:** 2026-09-09  
**Impact:** V05, V14 validations cannot run with real RL workload  

---

## Issue Summary

**Root Cause:** Brax 0.14.2 uses deprecated JAX APIs that have been removed in JAX 0.11.1

**Error:**
```
AttributeError: jax.device_put_replicated is deprecated; use jax.device_put instead.
```

**Location:** `workloads/rl_routine.py` line 122 → `brax/training/agents/ppo/train.py` line 756

---

## Investigation

### Version Incompatibility

**Current Environment:**
- brax: 0.14.2 (released ~2024)
- jax: 0.11.1 (released ~2026)
- jaxlib: (matching jax)

**Problem:** Brax 0.14.2 was written for older JAX API before `jax.device_put_replicated` was deprecated and removed.

### Import Path Changes Fixed

**Initial problem:** Code imported `from brax.training import ppo` but brax 0.14.2 has `from brax.training.agents.ppo import train`

**Fixed:**
- Changed: `from brax.training import ppo` → `from brax.training.agents.ppo import train as ppo_train`
- Changed: `from brax.training.agents.ppo import networks as ppo_networks`
- Updated `ppo.train()` → `ppo_train.train()`
- Updated `ppo.make_ppo_networks()` → `ppo_networks.make_ppo_networks()`
- Fixed network_factory signature to accept `(obs_shape, action_size, preprocess_observations_fn)`

**Result:** Import errors resolved, but runtime error remains due to deprecated JAX API usage inside brax.

---

## Resolution Options

### Option 1: Downgrade JAX (Recommended)

**Action:** Downgrade to JAX version compatible with brax 0.14.2

**Commands:**
```bash
pip install 'jax<0.5.0' 'jaxlib<0.5.0'
```

**Pros:**
- Brax 0.14.2 will work immediately
- No code changes needed
- Known stable combination

**Cons:**
- Using older JAX version
- May conflict with other dependencies

**Risk:** Low (brax explicitly depends on jax, so compatible versions exist)

### Option 2: Upgrade Brax

**Action:** Upgrade to latest brax that supports JAX 0.11.1

**Commands:**
```bash
pip install --upgrade brax
```

**Pros:**
- Latest brax version
- Modern JAX API

**Cons:**
- API changes may require code updates
- Brax 0.15+ might have breaking changes
- Unclear if brax has been updated for JAX 0.11.1

**Risk:** Medium (API surface may have changed significantly)

### Option 3: Use Brax Fork/Patch

**Action:** Fork brax or monkey-patch the deprecated API calls

**Pros:**
- Keep current versions
- Minimal changes

**Cons:**
- Maintenance burden
- Hacky solution
- May break other brax features

**Risk:** High (unmaintainable)

### Option 4: Defer Real RL Workload

**Action:** Continue using proxy objective for V05/V14 validations

**Pros:**
- Unblocks immediate work
- No environment changes

**Cons:**
- V05 gate criterion: "real RL task" not met
- V14 gate criterion: "day-one walk" not functional
- Tier 0 incomplete (BUILD_PROGRAM requirement: "functional day-one workload")

**Risk:** Low for short-term progress, but blocks Tier 0 gate

---

## Recommendation

**Immediate (Phase 0):** Option 4 - Defer real RL workload, use proxy for now

**Week 1 (Specification Reconciliation):** Decide whether to:
- Downgrade JAX (Option 1) if RL workload is Tier 0 requirement
- Amend LaTeX/BUILD_PROGRAM to make RL workload optional (checklist Item 4 allows this)

**Rationale:**
- Phase 0 goal: unblock immediate work (namespace collision FIXED ✓)
- Real RL workload is Tier 0 requirement per checklist Item 4
- Week 1 Day 1-3 Work Breakdown should include JAX downgrade if RL required
- Week 4 Day 1-2 can amend BUILD_PROGRAM_v3.md if RL deemed non-essential

---

## Current Workaround

**Status:** `JAX_AVAILABLE = True` but `rl_routine()` raises `AttributeError` at runtime

**V05 Validation:** Uses proxy objective (not real brax evaluation)  
**V14 Validation:** Cannot run "day-one walk" test  

**Code State:**
- Import paths fixed in `workloads/rl_routine.py` (committed)
- Runtime error documented here
- No temporary workaround implemented

---

## Impact Assessment

### Validations Blocked

| Validation | Status | Impact |
|------------|--------|--------|
| V05 | Uses proxy | Gate criterion "real RL task" not met |
| V14 | Cannot run | Gate criterion "day-one walk" blocked |

### Tier 0 Gate Impact

**Checklist Item 4:** "Tier 0 includes GP+qLogEI, required defaults, both executors, **functional day-one workload**, or LaTeX amended"

**Current State:** day-one workload NOT functional → Tier 0 gate BLOCKED unless LaTeX amended

**Resolution Path:**
1. Week 1: Decide if RL workload essential to Tier 0
2. If YES: Downgrade JAX during Week 1 Day 1-3
3. If NO: Amend BUILD_PROGRAM_v3.md Tier 0 section to remove RL requirement

---

## Next Steps

1. **Phase 0 Complete:** Namespace collision fixed ✓, brax issue documented
2. **Update Phase Marker:** Move to Week 1 Day 1 (Work Breakdown Spreadsheet)
3. **Week 1 Day 1-3:** Include JAX downgrade decision in work breakdown
4. **Week 4 Day 1-2:** Reflect decision in BUILD_PROGRAM_v3.md Tier 0 section

---

## File Changes Made

**workloads/rl_routine.py:**
- Line 30-37: Updated imports to use `brax.training.agents.ppo.train` and `.networks`
- Line 115-120: Updated network_factory signature to accept brax 0.14.2 parameters
- Line 123: Changed `ppo.train()` to `ppo_train.train()`

**Status:** Imports work, runtime blocked by deprecated JAX API in brax internals

---

**Document Status:** Complete  
**Approval:** Not required (investigation document)  
**Next Review:** Week 1 Day 1-3 (work breakdown decision point)
