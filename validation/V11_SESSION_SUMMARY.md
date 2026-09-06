# V11 Validation Session Summary

**Date:** 2026-09-06  
**Session focus:** V11 validation campaign pilot and saturation analysis  
**Time invested:** ~1.5 engineer-days  
**Status:** Pilot complete, confirmatory blocked on task redesign decision

---

## Work Completed

### 1. πBO Correctness Fix (0.5d)
**Critical bug:** `PriorWeightedAcquisition` applied prior weighting multiplicatively, which inverts preference when qLogEI is negative (the common regime once incumbent is good). High prior made negative values more negative, steering away from the prior-favored region.

**Fix:** Additive log-space weighting: `qLogEI_weighted(x) = qLogEI(x) + (β/n)·log(π(x))`

**Impact:** V11a's `implementation_requirement` specifies testing the actual πBO decay multiplier. With the bug, the campaign would have measured priors hurting when they help.

**Verification:** New regression test forces negative qLogEI regime and asserts correct preference ordering. All 7 πBO tests passing.

### 2. V11 Campaign Infrastructure (0.5d)
- **v11_tasks.py:** Four acceptance tasks with frozen bounds, declared optima, folklore/wrong priors
- **v11_campaign.py:** Paired-cluster bootstrap, Holm correction (tier1_gate family m=6), pilot/confirmatory modes
- **run_v11_pilot.py:** Write-artifact-before-summarise pattern to survive summary crashes
- **size_v11_confirmatory.py:** Simulation-based power sizing from pilot variance upper bound
- **probe_v11_saturation.py:** Trial-budget sweep to measure headroom (gap to declared optimum)

### 3. V11 Pilot Execution (0.3d)
- 120 studies (4 tasks × 3 arms × 2 methods × 5 replicates)
- Elapsed: 17.6 minutes
- Missingness: 0/40 blocks (0%)
- Artifact: `validation/results/v11_pilot.json` (35 KB)

**Results:**
- V11a: point +0.061, lower bound −0.00014 (threshold 0.0) → **inconclusive**
- V11b: point −0.027, lower bound −0.111 (threshold −0.10) → **inconclusive**

### 4. Saturation Diagnosis (0.2d)
**Finding:** GP+qLogEI no-prior baseline reaches declared optimum within 0.002–0.005% of span on all four tasks, leaving no headroom for V11a's superiority estimand.

**Evidence:**
- branin_2d: 0.00006 normalized gap at n=25
- hartmann_3d: 0.00002 normalized gap
- rl_proxy_3d: 0.00001 normalized gap (after correcting mis-declared optimum 95.0 → 96.302)
- sampler_proxy_2d: 0.00002 normalized gap

**Saturation probe results:**
- πBO: saturated at n=10 (0.0007 min headroom), only n=5 leaves room (+0.041) but too thin (4 GP proposals)
- PriorBand: saturated at n=15 (0.0058 min headroom)

**Root cause:** All four tasks are smooth low-dimensional analytic functions (2D–3D) that GP solves efficiently.

---

## Key Decisions

### Recommendation overturned by evidence
Initial analysis suggested n_trials=10 for πBO. Saturation probe disproved this—πBO already saturated at n=10. Updated recommendation to Option B (harder tasks) or Option E (escalate).

### Task defect corrected
rl_proxy_3d declared optimum was 95.0; global optimizer found true maximum 96.302. Corrected both the objective function center and declared_optimum. Folklore prior separation verified (7.8 prior widths from wrong_center).

---

## Deliverables

### Code (committed as dc78dfe)
- `validation/v11_tasks.py` (460 lines)
- `validation/v11_campaign.py` (544 lines)  
- `validation/run_v11_pilot.py` (73 lines)
- `validation/size_v11_confirmatory.py` (267 lines)
- `validation/probe_v11_saturation.py` (119 lines)

### Documentation (committed as dc78dfe, 09dc83e)
- `validation/V11_PILOT_REPORT.md` (203 lines): saturation evidence, five options, updated recommendation
- `validation/V11_TASK_REDESIGN_OPTIONS.md` (163 lines): detailed analysis of redesign paths

### Artifacts
- `validation/results/v11_pilot.json`: 120 study results, test statistics, prior support verification
- `validation/results/v11_saturation_probe.json`: headroom by task/method/budget

### Progress tracking (committed as 648aff8)
- Updated `docs/TIER1_PROGRESS_SUMMARY.md`: 43/70 days (61%), Priors 11/13d complete
- Gate status: 1/7 validations passing (V06), V11a/V11b blocked on redesign

---

## Blocking Issue

**V11 task saturation blocks gate criteria V11a/V11b.**

Current tasks leave no headroom for demonstrating prior value because no-prior baseline already wins. Confirmatory campaign cannot proceed without task redesign.

---

## Options for Resolution

### Option B: Harder Tasks (Recommended, ~3d)
Replace 2–3 tasks with higher-dimensional or multi-modal objectives:
- Hartmann 6D (replace hartmann_3d)
- Ackley 10D (replace sampler_proxy_2d)  
- Levy 8D (replace branin_2d)

**Justification:** Addresses root cause, moderate effort, no protocol violation. If harder tasks still saturate, that's a legitimate finding (GP strong enough that priors add little) → demote to opt-in per register demotion rule.

**Effort:** 0.5d task selection/implementation + 0.5d bounds/priors + 0.5d pilot + review = 3d

### Option E: Escalate to PI (~0.5d + review latency)
Pause pending design review. Draft escalation memo with pilot report attached, request approval for Option B or alternative direction.

**When appropriate:** If task redesign decision requires PI buy-in before committing effort.

### Option D: V11b Only (Fallback, ~0.75d)
Drop V11a (superiority), run V11b (non-inferiority) confirmatory only. Result: priors ship as opt-in (safe but unproven helpful), not default-on.

**When appropriate:** Timeline pressure or PI redirect to "test safety now, defer effectiveness."

---

## Lessons Learned

1. **Pilot-driven design:** Saturation discovered in 17.6-minute pilot rather than after 20-replicate confirmatory (saved ~6 hours of wasted compute)

2. **Probe before commit:** Initial n=10 recommendation looked reasonable from pilot variance; probe disproved it with direct evidence

3. **Write-first pattern:** Two prior pilot attempts lost to AttributeErrors in summary code; restructuring to write artifact before summarising prevented loss

4. **Test the edge case:** πBO inversion bug only manifested in negative qLogEI regime (not covered by existing tests); added regression test for the case the old code got backwards

5. **Task difficulty matters:** Analytic benchmarks efficient for unit tests but may lack realism for demonstrating method value—acceptance tasks need enough difficulty that baseline leaves room for improvement

---

## Next Steps

**Immediate (user decision required):**
1. Choose path: Option B (harder tasks), Option E (escalate), or Option D (V11b only)
2. If Option B: approve candidate tasks (Hartmann 6D, Ackley 10D, Levy 8D)

**Upon approval:**
1. Implement replacement tasks (~1d)
2. Re-pilot with new tasks (~0.5d)
3. Re-size from new pilot variance (~0.25d)
4. Proceed to confirmatory if power adequate

**Alternative work (not blocked):**
- MO veto logic tests (~1.5d)
- Workloads implementation (15d)
- Remaining validation campaigns (V06, V09, V10, V13)

---

## Cost Summary

**Time invested this session:** 1.5 engineer-days  
**Remaining to complete V11:** 2–4 days depending on redesign path chosen  
**Tier 1 overall progress:** 43/70 days complete (61%), 27 days remaining
