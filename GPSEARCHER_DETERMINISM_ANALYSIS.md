# GPSearcher Determinism Root Cause Analysis

**Date:** 2026-09-09  
**Issue:** V01 GP validation fails with KS=0.20 > 0.10 threshold  
**Symptom:** Two GPSearcher runs with same seed produce different results  

---

## Code Trace: Where Randomness Enters

### 1. Initial Random Phase (Lines 67-72)
```python
if len(self.history) < self.initial_random_samples:
    return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))
```
**Analysis:**
- Uses `self.rng` (numpy RandomState) seeded at init
- Controlled by GPSearcher seed ✓
- **Deterministic:** Yes

### 2. GP Fitting (Lines 78-82)
```python
gp = SingleTaskGP(X_train, Y_train)
mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
fit_gpytorch_mll(mll)
```
**Analysis:**
- BoTorch GP initialization
- MLE optimization for hyperparameters
- **Question:** Does `fit_gpytorch_mll()` use torch RNG?

### 3. Acquisition Optimization (Lines 84-92)
```python
qLogEI = qLogExpectedImprovement(gp, best_f=best_f)
bounds = self._get_bounds()
candidate, acq_value = optimize_acqf(
    qLogEI,
    bounds=bounds,
    q=1,
    num_restarts=self.num_restarts,  # 10 restarts
    raw_samples=512,  # Random initialization
)
```
**Analysis:**
- `optimize_acqf()` uses L-BFGS-B optimization
- `raw_samples=512` generates random starting points
- `num_restarts=10` runs 10 independent optimizations
- **Question:** Does BoTorch use torch.random for raw_samples?

---

## Root Cause Hypothesis

### Primary Suspect: torch Random State Not Controlled

**Evidence from BoTorch source:**

`optimize_acqf()` internally calls:
1. `gen_batch_initial_conditions()` - generates random starting points
2. Uses `torch.rand()` or `torch.randn()` without explicit seed
3. Each restart uses different random initialization

**Code path:**
```
optimize_acqf()
  └─> gen_batch_initial_conditions(raw_samples=512)
       └─> torch.rand(n, d)  # Uses global torch RNG!
```

### Secondary Suspect: GP Fitting Optimization

`fit_gpytorch_mll()` may use torch random state for:
- Parameter initialization
- Optimization noise/jitter
- Numerical stability adjustments

---

## Verification Test

Let me check if torch seed is set anywhere in our code:

```bash
grep -r "torch.manual_seed" hponas/
grep -r "torch.seed" hponas/
```

**Expected:** No results (torch seed not controlled)

---

## Why This Causes KS=0.20 Difference

### Scenario: Two runs with seed=43

**Run 1:**
1. Torch global RNG state: uninitialized (system-dependent)
2. `optimize_acqf()` generates raw_samples from torch.rand()
3. L-BFGS finds local optimum A
4. Suggests config_A

**Run 2:**
1. Torch global RNG state: different (system-dependent)
2. `optimize_acqf()` generates different raw_samples
3. L-BFGS finds local optimum B (different from A)
4. Suggests config_B

**Result:**
- Acquisition landscape has multiple local optima
- Different random initializations find different optima
- Over 30 trials, this accumulates to KS=0.20 difference

---

## Why Initial Random Phase IS Deterministic

**Observation from V01 test:**
```
Our mean score: -0.0450
Ref mean score: -0.0440
```

**Analysis:**
- Means are very close (-0.0450 vs -0.0440)
- Only 0.001 difference (~2% relative error)
- KS=0.20 indicates distribution shape differs, not just mean

**Interpretation:**
- First 5 trials (random phase): probably identical
- Next 25 trials (GP phase): different due to torch RNG
- Small mean difference confirms most trials are similar
- Large KS indicates ordering/distribution differs

---

## The Fix: Set Torch Seed

### Option 1: Set torch seed at GPSearcher init
```python
def __init__(self, search_space, seed=None, ...):
    super().__init__(search_space, seed)
    self.rng = np.random.RandomState(seed)
    
    # FIX: Set torch seed
    if seed is not None:
        torch.manual_seed(seed)
```

**Pros:** Simple, one-time setup  
**Cons:** Global state, affects other torch code

### Option 2: Set torch seed before each suggest()
```python
def suggest(self) -> Config:
    # FIX: Set torch seed before GP operations
    if self.seed is not None:
        torch.manual_seed(self.seed + len(self.history))
```

**Pros:** More controlled, seed varies per iteration  
**Cons:** More invasive, need to store seed

### Option 3: Pass generator to optimize_acqf()
```python
generator = torch.Generator()
if self.seed is not None:
    generator.manual_seed(self.seed + len(self.history))

candidate, acq_value = optimize_acqf(
    qLogEI,
    bounds=bounds,
    q=1,
    num_restarts=self.num_restarts,
    raw_samples=512,
    generator=generator,  # Pass explicit generator
)
```

**Pros:** Most explicit, no global state pollution  
**Cons:** Need to check if optimize_acqf() supports generator arg

---

## Recommended Fix: Option 2 (Seed per iteration)

**Rationale:**
1. Each suggest() call should be deterministic given seed + history
2. Varying seed per iteration prevents correlation artifacts
3. Allows resuming from checkpoint deterministically

**Implementation:**
```python
def __init__(self, search_space, seed=None, ...):
    super().__init__(search_space, seed)
    self.seed = seed  # Store seed for later use
    self.rng = np.random.RandomState(seed)
    
def suggest(self) -> Config:
    # Set torch seed before GP operations (deterministic given seed + history length)
    if self.seed is not None:
        torch.manual_seed(self.seed + len(self.history))
    
    # Initial random phase
    if len(self.history) < self.initial_random_samples:
        return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))
    
    # ... rest of GP suggest logic
```

**Expected Result:**
- Two runs with same seed produce identical suggestions
- V01 validation: KS < 0.01, p > 0.99 (perfect match)

---

## Testing the Fix

### Test 1: Determinism within single run
```python
searcher1 = GPSearcher(space, seed=42)
searcher2 = GPSearcher(space, seed=42)

for i in range(30):
    c1 = searcher1.suggest()
    c2 = searcher2.suggest()
    assert c1.values == c2.values  # Should be identical
    
    # Observe same result
    searcher1.observe(Result(..., objective_value=f(c1)))
    searcher2.observe(Result(..., objective_value=f(c2)))
```

### Test 2: V01 validation with fix
```bash
python validation/v01_wrapper_parity.py
```

**Expected:**
- KS < 0.10 (probably < 0.01)
- p > 0.05 (probably > 0.99)
- Status: ✓ PASSED

---

## Impact on Other Code

### Files potentially affected:
1. `hponas/searchers/gp_searcher.py` - PRIMARY (needs fix)
2. `tests/conformance/test_searcher_contract.py` - Should now pass with tighter tolerance
3. `validation/v01_wrapper_parity.py` - Should now pass

### Files NOT affected:
- RandomSearcher (only uses numpy RNG)
- SobolSearcher (only uses scipy, which we control)
- LocalExecutor (no torch usage)

---

## Alternative: Relax V01 Threshold

**If we decide NOT to fix GPSearcher:**

Could update V01 protocol to accept KS < 0.25 for GP test, acknowledging:
- "GP acquisition optimization has inherent numerical variation"
- "Approximate determinism acceptable for BO methods"

**Pros:** No code change required  
**Cons:** 
- Violates principle of deterministic replay
- Makes checkpoint resume less reliable
- Harder to debug differences in future

**Recommendation:** Fix the code, not the threshold

---

## Next Steps

1. **Implement fix** in GPSearcher.suggest()
2. **Run test** with test_searcher_contract.py determinism tests
3. **Re-run V01** validation
4. **Update RECOVERY_MASTER_PROGRAM** to reflect this as unplanned remediation work
5. **Document** in CONTRACT_SEMANTICS_v1.md that torch seed must be set

---

## Time Estimate

- Implement fix: 30 minutes
- Test fix: 30 minutes
- Re-run V01: 5 minutes
- Update documentation: 1 hour
- **Total: 2 hours**

---

**Status:** Root cause identified, fix designed, ready to implement  
**Risk:** Low - isolated change, clear test criteria  
**Priority:** High - blocks V01 validation gate
