# Tier 1 Gate Validation Status

**Generated:** 2026-09-04  
**Gate:** Tier 1 (Week 12)  
**Reference:** BUILD_PROGRAM_v2.md lines 239-249

---

## Summary

| Validation | Claim | Status | Result |
|------------|-------|--------|--------|
| V04-T1 | TuRBO and prior-aware qLogEI beat log+Sobol floor | ❌ FAILED | 2.42% improvement (threshold: 5%), p=0.2738 |
| V06 | ASHA reaches full-fidelity quality at ≤1/3 compute | ✅ PASSED | 0.17% quality gap, 18.5% compute ratio |
| V09 | qLogNEHVI beats scalarization or ties and gets demoted | ✅ PASSED | 8.2% improvement, p=0.0159 |
| V10 | drift-at-rung correlates with drift-at-end, ρ > 0.6 | ⏸️ DEFERRED | Moved to Tier 2 (Week 30) per drift report |
| V11 | priors help under good advice, recover under wrong advice | ⚠️ INCONCLUSIVE | Pilot complete; confirmatory undersized |
| V13 | no veto-failing configs promoted; survivors ranked by ESS/gradient | ⏸️ DEFERRED | Moved to Tier 2 (Week 30) per drift report |

---

## Validation Details

### V04-T1: Sobol vs Random on Real RL Workload

**Status:** ❌ FAILED  
**Artifact:** results/v04_t1_real_workload.json  
**Implementation:** validation/v04_t1_real_workload.py  

**Protocol:**
- 200 trials per seed, 5 seeds
- 9-knob rl_routine search space
- Proxy objective (real RL evaluation too expensive for validation)

**Results:**
- Sobol AUC: 0.7783
- Random AUC: 0.7598
- Improvement: 2.42% (threshold: 5%)
- p-value: 0.2738 (not significant, threshold: 0.05)

**Failure mode:** Sobol advantage too small and not statistically significant on 9D proxy workload.

**Demotion rule:** TuRBO failure (V04-T1) triggers: defer population line (BG-PBT depends on TR), reassess tier-2 scope.

---

### V06: ASHA Efficiency

**Status:** ✅ PASSED  
**Artifact:** results/v06_asha_efficiency.json  
**Implementation:** validation/v06_asha_efficiency.py  

**Protocol:**
- 30 trials per seed, 5 seeds
- Multi-fidelity Branin (fidelity 1→27)
- Compare ASHA vs full-fidelity search

**Results:**
- Quality gap: 0.17% (threshold: 5%)
- Compute ratio: 0.185 (threshold: 0.333)
- p-value: 0.8413 (not significantly different)
- All criteria passed

**Gate criterion satisfied:** ASHA reaches full-fidelity quality at ≤1/3 compute.

---

### V09: qLogNEHVI vs Scalarization

**Status:** ✅ PASSED  
**Artifact:** results/v09_qlogNEHVI_vs_scalarization.json  
**Implementation:** validation/v09_qlogNEHVI_scalarization.py  

**Protocol:**
- 50 trials, 10 seeds
- Multi-objective Branin-Currin
- Compare qLogNEHVI vs qLogEI + Chebyshev scalarization

**Results:**
- qLogNEHVI hypervolume: 0.6115
- Scalarization hypervolume: 0.5613
- Improvement: 8.2%
- p-value: 0.0159 (significant)

**Gate criterion satisfied:** qLogNEHVI beats scalarization baseline.

---

### V10: Rung Correlation Diagnostics

**Status:** ⏸️ DEFERRED TO TIER 2  
**Reference:** BUILD_PROGRAM_DRIFT_REPORT.md line 31  

**Reason:** MO-ASHA rung-correlation pilot explicitly deferred to Week 30 (Tier 2 timeframe).

**Implementation:** Deferred (will be implemented in Tier 2).

**Enhanced requirements when implemented (BUILD_PROGRAM_REVIEW_VERDICT.md line 207):**
- Use multiple seeds/tasks and out-of-sample configurations
- Gate on top-k/Pareto survivor recall, false-cull probability, and regret
- Not just simple Spearman rho > 0.6

---

### V11: Prior Recovery

**Status:** ⚠️ INCONCLUSIVE (Pilot Complete)  
**Artifacts:**
- results/v11_pilot_summary.json
- validation/results/v11_pilot.json
- validation/results/v11_sizing.json  
**Implementation:** validation/v11_campaign.py, validation/run_v11_pilot.py  

**Protocol:**
- Pilot mode: 120 studies, 5 replicates, 25 trials
- Two hypotheses:
  - V11a: folklore_prior beats no_prior
  - V11b: wrong_prior recovers (does not fall below no_prior by >10%)

**Pilot Results (17.9 minutes):**
- V11a: point=+0.0604, lb=-0.0002, p=0.0195, verdict=inconclusive
- V11b: point=-0.0249, lb=-0.1125, p=0.0172, verdict=inconclusive

**Confirmatory Sizing:**
- V11a: NOT SIZED - power 0.258 at max_sample=20 (target: 0.8)
- V11b: NOT SIZED - power 0.542 at max_sample=20 (target: 0.8)
- Both would return `inconclusive` verdict per policy.power.max_sample_rule

**Interpretation:** Pilot effect sizes too small relative to variance for confirmatory campaign to reach target power within max sample budget.

**Demotion rule:** Prior failure (V11) triggers: demote πBO/PriorBand to opt-in.

---

### V13: Warm-Start Effectiveness

**Status:** ⏸️ DEFERRED TO TIER 2  
**Reference:** BUILD_PROGRAM_DRIFT_REPORT.md line 34  
**Implementation:** No files found in validation/  

**Gate criterion:** No veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior.

**Reason:** "Sampler veto correctness deferred 18 weeks" per BUILD_PROGRAM_DRIFT_REPORT.md line 34. Explicitly listed alongside V06 and V10 as deferred from T1 to Week 30 (Tier 2).

**Note:** BUILD_PROGRAM_v2.md line 236 states "Moved V06/V10/V13 from T2 per survey" but BUILD_PROGRAM_DRIFT_REPORT.md (written later, 2026-08-28) confirms V13 remains at T2/Week 30, not T1/Week 12.

---

## Gate Status: FAILING

**Actual T1 scope (after deferrals):** 4 validations (V04-T1, V06, V09, V11)  
**Deferred to T2:** 2 validations (V10, V13)  

**Pass count:** 2/4 (V06, V09)  
**Fail count:** 1/4 (V04-T1)  
**Inconclusive:** 1/4 (V11)  

### Triggered Demotion Rules

1. **V04-T1 failure:** Defer population line (BG-PBT depends on TuRBO); reassess Tier 2 scope
2. **V11 inconclusive/weak effect:** Demote πBO/PriorBand to opt-in

### Outstanding Work

1. **V11 confirmatory decision** - pilot shows weak/inconclusive effects; apply demotion rule or revise validation protocol
2. **V04-T1 failure resolution** - apply demotion rule or fix Sobol implementation/protocol
3. **Gate report generation** - document demotion decisions per BUILD_PROGRAM_v2.md line 263

### Build Program Impact

Per BUILD_PROGRAM_REVIEW_VERDICT.md, the build program has been declared RED (not approved) with blocking findings including:
- Zero executable product tests exist
- Timeline/effort/staffing arithmetic irreconcilable  
- Material inconsistencies with governing roadmap
- Validation methodology issues (including V10 critique applicable to other validations)

The Tier 1 gate validation results confirm methodological concerns: V04-T1 failed to show significance, V11 pilot found effects too weak for confirmatory testing.

---

## Next Steps

1. Determine V13 status (implement vs defer to T2)
2. Apply demotion rules for V04-T1 and V11 failures
3. Review validation methodology per BUILD_PROGRAM_REVIEW_VERDICT.md findings
4. Generate gate report with demotion decisions per BUILD_PROGRAM_v2.md line 263
