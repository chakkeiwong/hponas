# V03 Round 6: Scheduler Test Additions

## Status
- **Previous kill score:** 87.52% (1592/1819)
- **Gap to 90%:** 46 kills needed
- **Target module:** schedulers (82 survivors, 36% of total)

## Tests Added (7 new tests)

### 1. `test_promote_n_promote_calculation_edge_case`
- **Targets:** `promote__mutmut_10` (n_promote = None mutation)
- **Tests:** When n_pop == eta exactly, all should be promoted
- **Kills:** Edge case in n_promote calculation

### 2. `test_promote_returns_correct_fidelity`
- **Targets:** `promote__mutmut_16`, `promote__mutmut_21`, `promote__mutmut_23`, `promote__mutmut_28`
- **Tests:** Promoted trials receive correct next fidelity value
- **Kills:** Return value structure and fidelity progression

### 3. `test_state_dict_preserves_structure`
- **Targets:** `state_dict__mutmut_12`, `state_dict__mutmut_16`
- **Tests:** state_dict() returns complete scheduler state with all keys
- **Kills:** Missing or malformed state dict structure

### 4. `test_state_dict_deep_copy_independence`
- **Targets:** `state_dict__mutmut_12` (copy.copy vs copy.deepcopy)
- **Tests:** Mutating returned state doesn't affect scheduler internals
- **Kills:** Shallow copy mutation in rungs field

### 5. `test_load_state_dict_restores_state`
- **Targets:** `load_state_dict__mutmut_15`, `load_state_dict__mutmut_19`
- **Tests:** Round-trip state serialization preserves trial state
- **Kills:** Incomplete state restoration

### 6. `test_promote_with_single_trial`
- **Targets:** `promote__mutmut_16` (max(1, ...) → max(2, ...))
- **Tests:** Single trial gets promoted (tests max(1, ceil(...)) logic)
- **Kills:** Off-by-one in minimum promotion count

### 7. Existing test enhanced: `test_promote_returns_correct_fidelity`
- Verifies both promoted trial count AND next fidelity values
- Closes gap in return value validation

## Expected Impact
- **Direct kills:** 8-12 from state_dict, load_state_dict, promote logic
- **Indirect kills:** 5-10 from better coverage of edge cases
- **Total expected:** 13-22 kills toward 46-kill gap

## Mutation Testing Run
- Started: Background task b1vclivut
- Expected duration: ~2 hours
- Will analyze results when complete

## Next Steps After Results
1. If ≥90% → Gate passed, move to next validation
2. If 88-89% → Analyze remaining survivors, add 2-3 targeted tests
3. If <88% → Investigate test failures, may need MOASHA tests
