# R7 Test Creation Guide - Survivor Analysis

**Use after R6 results show we need more kills to reach 90%**

---

## Step 1: Analyze Survivors by Module

```bash
python analyze_survivors.py
```

This shows:
- Total survivors by module
- Top methods with most survivors
- ROI-ranked priority targets

Expected output:
```
SURVIVOR ANALYSIS - 227 TOTAL SURVIVORS
====================================================================

By Module:
  schedulers                     82 ( 36.1%)
  searchers.random_searcher      46 ( 20.3%)
  executors.local_executor       31 ( 13.7%)
  ...
```

---

## Step 2: Deep Dive on Priority Module

Start with the module with most survivors (likely schedulers):

```bash
python analyze_survivors.py --module schedulers --show-diffs
```

This shows:
- Methods with most survivors
- Sample mutation IDs
- Actual mutation diffs

---

## Step 3: Inspect Individual Mutations

```bash
python -m mutmut show hponas.schedulers.xǁASHASchedulerǁpromote__mutmut_42
```

Look for patterns:
- **Boundary conditions**: `> 0` mutated to `>= 0`, `< len` to `<= len`
- **Logic inversions**: `if x` to `if not x`
- **Arithmetic**: `+ 1` to `- 1`, `* 2` to `/ 2`
- **Return values**: `return True` to `return False`
- **Error handling**: `raise X` to `pass`

---

## Step 4: Identify Untested Code Paths

For each survivor, ask:
1. **What code path does this mutation create?**
2. **What test would exercise that path?**
3. **What assertion would catch the mutation?**

### Example: Scheduler Rung Promotion

**Mutation:**
```diff
- if trial.rung < len(self.rungs) - 1:
+ if trial.rung <= len(self.rungs) - 1:
```

**What it does:** Tries to promote trials from the highest rung (which shouldn't happen)

**Test to kill it:**
```python
def test_scheduler_does_not_promote_from_highest_rung():
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    # Fill all rungs
    for i in range(10):
        trial_id = f"trial_{i}"
        scheduler.observe(trial_id, rung=0, score=i * 10)
        # Promote through all rungs
        for _ in range(2):  # 2 promotions to reach highest rung
            action = scheduler.decide(trial_id)
            if action == "promote":
                scheduler.observe(trial_id, rung=scheduler.get_rung(trial_id) + 1, score=i * 10)
    
    # Trial is now at highest rung (rung=2)
    trial_id = "trial_0"
    assert scheduler.get_rung(trial_id) == 2
    
    # Decide should NOT promote from highest rung
    action = scheduler.decide(trial_id)
    assert action != "promote"  # Should be "continue" or "stop"
```

---

## Step 5: Write Tests by Pattern

### Pattern A: Boundary Conditions

Target mutations: `>` ↔ `>=`, `<` ↔ `<=`, `== 0` ↔ `!= 0`

```python
def test_boundary_<specific_case>():
    # Setup at exact boundary
    # Call method
    # Assert correct boundary behavior
```

### Pattern B: Logic Inversions

Target mutations: `if x:` ↔ `if not x:`, `and` ↔ `or`

```python
def test_logic_<specific_case>():
    # Setup both True and False cases
    # Assert different outcomes
```

### Pattern C: Error Handling

Target mutations: `raise` → `pass`, `try/except` removal

```python
def test_raises_on_<invalid_input>():
    with pytest.raises(ExpectedError):
        method_call(invalid_input)
```

### Pattern D: State Transitions

Target mutations: Incorrect state updates

```python
def test_state_transition_<from>_to_<to>():
    # Setup initial state
    # Trigger transition
    # Assert final state is correct
```

---

## Step 6: Scheduler-Specific Test Examples

Based on typical scheduler survivors:

### Test 1: Rung Boundary Conditions
```python
def test_asha_rung_index_boundary():
    """Test rung index stays within valid bounds."""
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    scheduler.observe("trial_0", rung=0, score=100)
    
    # Promote to rung 1
    scheduler.decide("trial_0")
    scheduler.observe("trial_0", rung=1, score=100)
    
    # Promote to rung 2 (highest)
    scheduler.decide("trial_0")
    scheduler.observe("trial_0", rung=2, score=100)
    
    # Should not promote beyond highest rung
    action = scheduler.decide("trial_0")
    assert action in ["continue", "stop"]
```

### Test 2: Empty Rung Handling
```python
def test_asha_handles_empty_rung():
    """Test scheduler handles empty rungs correctly."""
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    
    # No trials observed yet
    # Attempting to get best from empty rung should handle gracefully
    result = scheduler._get_best_trials_from_rung(rung=0, k=1)
    assert result == []  # Should return empty list, not crash
```

### Test 3: Promotion Ratio Edge Cases
```python
def test_asha_promotion_ratio_floor():
    """Test promotion count rounds correctly."""
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    
    # Add 4 trials to rung 0
    # reduction_factor=3 means promote 4/3 = 1.33 → should promote 1, not 2
    for i in range(4):
        scheduler.observe(f"trial_{i}", rung=0, score=i * 10)
    
    promoted_count = 0
    for i in range(4):
        action = scheduler.decide(f"trial_{i}")
        if action == "promote":
            promoted_count += 1
    
    assert promoted_count == 1  # Should promote floor(4/3) = 1
```

### Test 4: Score Comparison Edge Cases
```python
def test_asha_score_equality_handling():
    """Test tie-breaking when scores are equal."""
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    
    # All trials have same score
    for i in range(6):
        scheduler.observe(f"trial_{i}", rung=0, score=50.0)
    
    # Should still promote correct number (6/3 = 2)
    promoted = []
    for i in range(6):
        action = scheduler.decide(f"trial_{i}")
        if action == "promote":
            promoted.append(f"trial_{i}")
    
    assert len(promoted) == 2
```

### Test 5: Sequential Promotion
```python
def test_asha_sequential_promotion_state():
    """Test state consistency during sequential promotions."""
    scheduler = ASHAScheduler(max_t=27, reduction_factor=3)
    
    # Observe 9 trials at rung 0
    for i in range(9):
        scheduler.observe(f"trial_{i}", rung=0, score=i * 10)
    
    # Promote 3 to rung 1
    for i in range(9):
        if scheduler.decide(f"trial_{i}") == "promote":
            scheduler.observe(f"trial_{i}", rung=1, score=i * 10)
    
    # Check rung 1 has exactly 3 trials
    rung_1_count = len([t for t in scheduler._trials.values() if t.rung == 1])
    assert rung_1_count == 3
```

---

## Step 7: Implementation Workflow

1. **Pick module** (start with schedulers - 82 survivors)
2. **Sample 10 mutations** using `analyze_survivors.py --module schedulers`
3. **Inspect each mutation** with `mutmut show <id>`
4. **Identify pattern** (boundary, logic, state, error)
5. **Write test** following pattern templates above
6. **Verify test fails** on mutated code
7. **Verify test passes** on original code
8. **Repeat** until 10-15 tests written

---

## Step 8: Run R7

After adding tests:

```bash
# Verify tests pass
pytest tests/unit/test_schedulers.py -v

# Run mutation testing
rm -rf mutants/ && python -m mutmut run
```

Expected: 87.5% → 90.5%

---

## ROI Estimates

**Schedulers (82 survivors):**
- 10 tests → 15-25 kills (18-30%)
- Focus: rung boundaries, promotion logic, empty rungs

**RandomSearcher/Sobol (46 survivors):**
- 5 tests → 10-15 kills (22-33%)
- Focus: boundary clamps, state consistency

**Space/Types (38 survivors):**
- 5 tests → 10-15 kills (26-40%)
- Focus: validation, type conversions

**Total: 20 tests → 35-55 kills (enough to reach 90%)**

---

## Quick Reference Commands

```bash
# Check R6 results
python quick_mutation_check.py

# Analyze all survivors
python analyze_survivors.py

# Deep dive on module
python analyze_survivors.py --module schedulers --show-diffs

# Inspect specific mutation
python -m mutmut show <mutation_id>

# Run new tests
pytest tests/unit/test_schedulers.py -v -k <test_name>

# Run R7
rm -rf mutants/ && python -m mutmut run
```
