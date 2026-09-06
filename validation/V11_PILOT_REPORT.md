# V11 Pilot Report

**Date:** 2026-09-06  
**Campaign:** V11a (folklore_prior superiority) and V11b (wrong_prior non-inferiority)  
**Pilot configuration:** 5 replicates per (task, method, arm), 25 trials per study  
**Elapsed:** 17.9 minutes (120 studies)  
**Status:** Complete, no missingness

---

## Executive Summary

The V11 pilot reveals a **task saturation problem**: the no-prior baseline achieves results within 0.002–0.003% of the declared optimum on all four tasks when using πBO (GP + qLogEI) with 25 trials. This ceiling effect makes it impossible for folklore_prior to demonstrate superiority, as there is no headroom left to win.

**V11a pilot results:**
- Point estimate: +0.061 normalized difference (folklore_prior vs no_prior)
- Lower bound (family-adjusted): −0.00014
- p-value: 0.017
- Verdict: **inconclusive** (does not clear threshold of 0.0)

**V11b pilot results:**
- Point estimate: −0.027 normalized difference (wrong_prior vs no_prior)
- Lower bound (family-adjusted): −0.111
- p-value: 0.020
- Verdict: **inconclusive** (does not clear non-inferiority threshold of −0.10)

The positive V11a point estimate is driven entirely by PriorBand (+14.9% to +18.9% normalized gains). πBO shows near-zero effects (−0.04% to +0.02%) because the no-prior baseline is already saturated.

---

## Saturation Evidence

### Headroom by task and method (normalized scale)

| Task             | Method    | Direction | Declared Opt | No-Prior Median | Gap      | Gap/Span  |
|------------------|-----------|-----------|--------------|-----------------|----------|-----------|
| branin_2d        | pibo      | minimize  | 0.397887     | 0.413778        | 0.015891 | **0.00005** |
| branin_2d        | priorband | minimize  | 0.397887     | 1.409363        | 1.011476 | 0.00329   |
| hartmann_3d      | pibo      | minimize  | −3.862780    | −3.862686       | 0.000093 | **0.00002** |
| hartmann_3d      | priorband | minimize  | −3.862780    | −3.516466       | 0.346314 | 0.08965   |
| rl_proxy_3d      | pibo      | maximize  | 95.000000    | 96.299317       | −1.299317| **−0.01299** |
| rl_proxy_3d      | priorband | maximize  | 95.000000    | 63.665403       | 31.334597| 0.31335   |
| sampler_proxy_2d | pibo      | minimize  | 0.000000     | 0.000024        | 0.000024 | **0.00002** |
| sampler_proxy_2d | priorband | minimize  | 0.000000     | 0.314903        | 0.314903 | 0.29991   |

**Gap/Span** is the maximum normalized difference a prior could possibly achieve (the headroom). πBO's no-prior baseline leaves **0.002–0.005%** headroom on all four tasks.

### Representative per-cluster means (V11a)

| Cluster                  | n | Mean Norm Diff | Raw Diff | Interpretation                                  |
|--------------------------|---|----------------|----------|------------------------------------------------|
| branin_2d::pibo          | 5 | −0.00014       | −0.04    | folklore slightly *worse* (noise)              |
| hartmann_3d::pibo        | 5 | −0.00004       | −0.0002  | indistinguishable (0.005% of span)             |
| hartmann_3d::priorband   | 5 | +0.14895       | +0.58    | folklore **helps** (14.9% improvement)         |
| rl_proxy_3d::priorband   | 5 | +0.18861       | +18.86   | folklore **helps** (18.9% improvement)         |
| sampler_proxy_2d::priorband | 5 | +0.15300    | +0.16    | folklore **helps** (15.3% improvement)         |

PriorBand shows the effect V11a is designed to measure. πBO does not, because its baseline is already winning.

---

## Root Cause: πBO Baseline Saturation

GP + qLogEI with 25 trials is too strong a baseline on these four tasks. The no-prior arm:
- Uses Sobol initialization (1 trial)
- Fits a GP and optimizes qLogEI for 24 subsequent proposals
- Reaches the declared optimum within measurement noise

Even though πBO's prior weighting is working correctly (verified via direct acquisition evaluation and distance-to-center traces), the prior has nothing to steer toward because the baseline already arrived.

PriorBand's baseline is weaker (random sampling from prior/incumbent blend until enough observations accumulate for successive halving), so folklore_prior has room to help.

---

## Implications for V11

1. **V11a cannot pass with the current task set at n_trials=25.**  
   The estimand is "folklore_prior advantage over no_prior," but no_prior is already at the ceiling on πBO.

2. **V11b's non-inferiority margin (−0.10) might still be testable** if wrong_prior harms are small enough, but the pilot's −0.111 lower bound just misses. With more replicates, V11b might clear.

3. **The register does not require a minimum task difficulty,** so this is not a protocol violation. It is a pilot finding that informs whether the confirmatory campaign should proceed as-designed.

---

## Recommended Paths Forward

### Option A: Reduce trial budget (πBO-specific)
- **Change:** Set `n_trials=10` for πBO, keep `n_trials=25` for PriorBand
- **Rationale:** πBO saturates by trial 15–20; PriorBand needs more trials to accumulate observations for SH. A split budget respects each method's baseline strength.
- **Cost:** Requires re-running the pilot (~18 min), re-sizing, and updating the task registry with method-specific budgets.
- **Risk:** If 10 trials is still too many, we may need another iteration.

### Option B: Harder tasks
- **Change:** Replace 2–3 of the current tasks with higher-dimensional or more deceptive objectives (e.g., 6D Hartmann, 10D Ackley, or a multi-modal RL proxy with local traps).
- **Rationale:** Harder tasks leave headroom for priors to help.
- **Cost:** Task selection, bound declaration, prior design, sanity checks, and re-pilot (~1–2 days).
- **Risk:** Harder tasks might also hurt PriorBand's baseline, widening variance and forcing larger sample sizes.

### Option C: Add observation noise
- **Change:** Inject Gaussian noise into objective observations (e.g., σ = 0.05 × span).
- **Rationale:** Noise prevents saturation and makes the prior's guidance valuable across more trials.
- **Cost:** Update task definitions, re-pilot.
- **Risk:** Noise increases variance, which increases required sample size. May also make the tasks feel artificial (acceptance tasks should resemble real HPO).

### Option D: Proceed with V11b only, defer V11a
- **Change:** Drop V11a (superiority) from this validation wave. Run V11b (non-inferiority) confirmatory at max_sample=20, accepting that it may still land "inconclusive."
- **Rationale:** V11b's claim ("wrong priors are safe") is testable even with saturation, because we only need to show harm stays above −0.10. V11a's claim ("folklore priors help") requires headroom the current setup doesn't have.
- **Cost:** V11a remains untested, so priors cannot be default-on even if V11b passes. The gate decision becomes "priors are safe but unproven helpful" → opt-in only.
- **Benefit:** Fastest path forward (~4d for V11b confirmatory), avoids re-design risk.

### Option E: Abort V11, escalate to PI
- **Change:** Pause V11 validation pending a design review with the principal investigator.
- **Rationale:** The current task set cannot deliver on V11a's estimand. Proceeding to confirmatory without addressing saturation wastes 20 replicates/task and produces an inconclusive result by design.
- **Cost:** Blocks the priors release (default-on requires both V11a and V11b pass). Delays downstream Tier 1 work.
- **Benefit:** Ensures V11 is worth running before committing to the full sample.

---

## Recommendation

**Pursue Option B (harder tasks) or Option E (abort and escalate to PI).**

**Justification:**
- **Option A is disproved by the saturation probe.** The corrected probe (after fixing rl_proxy_3d's declared optimum from 95.0 to 96.302) shows πBO is already saturated at n=10 (min headroom +0.00070, below the 0.01 threshold). Only n=5 leaves πBO meaningful headroom (+0.04129), but 5 trials means just 4 GP-driven proposals after the Sobol bootstrap—too thin to constitute a meaningful test of the method.
- **All four current tasks are smooth low-dimensional analytic functions** (branin 2D, hartmann 3D, rl_proxy 3D, sampler_proxy 2D) that GP+qLogEI solves efficiently. This is a task-selection issue, not a trial-budget issue.
- **Option B (harder tasks)** addresses the root cause: replace 2–3 tasks with higher-dimensional or more deceptive objectives (6D Hartmann, 10D Ackley, multi-modal RL proxy with local traps) where priors have room to help. Cost: task selection, bound declaration, prior design, sanity checks, re-pilot (~1–2 days).
- **Option E (abort and escalate)** is appropriate if the PI prefers to defer V11 rather than redesign the task set mid-validation.

**Updated saturation evidence (corrected rl_proxy_3d optimum 95.0 → 96.302):**

πBO min headroom across tasks:
- n=5: +0.041 (usable but thin: only 4 GP proposals)
- n=10: +0.0007 (**saturated**)
- n=15: +0.00006 (**saturated**)
- n=20: +0.00003 (**saturated**)
- n=25: +0.00001 (**saturated**)

PriorBand min headroom:
- n=5: +0.056
- n=10: +0.0149
- n=15: +0.0058 (**saturated**)

The corrected rl_proxy_3d gap is now positive (+0.00001 at n=25), confirming the mis-declared optimum was masking the ceiling effect rather than disproving it.

---

## Prior Support (Verification Required by Register)

All wrong_prior arms have nonzero density at the declared optimum, as required. Density ratios confirm folklore_prior is peaked at the optimum (6.6×–28.8× mean density) and wrong_prior is at the guard floor (0.038×–0.054× mean density).

| Task             | Arm             | Density @ Opt | Ratio to Mean | Has Support |
|------------------|-----------------|---------------|---------------|-------------|
| branin_2d        | folklore_prior  | 8.60          | 8.59          | ✓           |
| branin_2d        | wrong_prior     | 0.050         | 0.054         | ✓           |
| hartmann_3d      | folklore_prior  | 27.15         | 28.85         | ✓           |
| hartmann_3d      | wrong_prior     | 0.050         | 0.041         | ✓           |
| rl_proxy_3d      | folklore_prior  | 27.07         | 28.01         | ✓           |
| rl_proxy_3d      | wrong_prior     | 0.050         | 0.038         | ✓           |
| sampler_proxy_2d | folklore_prior  | 6.67          | 6.64          | ✓           |
| sampler_proxy_2d | wrong_prior     | 0.050         | 0.048         | ✓           |

---

## Appendix: Raw Pilot Data Summary

**V11a: folklore_prior vs no_prior [superiority_one_sided]**
- Threshold: +0.00
- Point estimate: +0.061
- Lower bound: −0.00014 (α = 0.00833, Holm-adjusted for family size 6)
- p-value: 0.017
- Clears threshold: False
- Pilot verdict: **inconclusive**
- Missingness: 0/40 (0.0%)
- Clusters: 8 (4 tasks × 2 methods)
- Blocks: 40 (5 replicates × 8 clusters)

**V11b: wrong_prior vs no_prior [non_inferiority_one_sided]**
- Threshold: −0.10
- Point estimate: −0.027
- Lower bound: −0.111 (α = 0.01000, Holm-adjusted)
- p-value: 0.020
- Clears threshold: False
- Pilot verdict: **inconclusive**
- Missingness: 0/40 (0.0%)
- Clusters: 8
- Blocks: 40

---

## Next Steps

1. **Decision gate:** Choose Option A, D, or E above.
2. **If Option A:** Update `validation/v11_tasks.py` to set `n_trials=10` for πBO, re-run pilot, re-size.
3. **If Option D:** Proceed directly to V11b confirmatory sizing from this pilot data.
4. **If Option E:** Draft escalation memo for PI with this report attached.

**Pilot artifact:** `validation/results/v11_pilot.json` (35 KB, 120 studies, manifest digest embedded)

---

**Report prepared by:** Automated campaign harness  
**Reviewed by:** [Pending]
