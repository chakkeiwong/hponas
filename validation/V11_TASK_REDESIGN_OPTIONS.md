# V11 Task Redesign Options

**Date:** 2026-09-06  
**Context:** V11 pilot revealed task saturation—GP+qLogEI no-prior baseline reaches declared optimum within 0.002–0.005% of span on all four current tasks, leaving no headroom for V11a's superiority claim to detect.

**Root cause:** All four current tasks (branin 2D, hartmann 3D, rl_proxy 3D, sampler_proxy 2D) are smooth low-dimensional analytic functions that GP solves efficiently.

---

## Option B: Harder Tasks (Recommended)

Replace 2–3 of the current tasks with higher-dimensional or more deceptive objectives where priors have room to help.

### Candidate replacements:

**1. Hartmann 6D** (replace hartmann_3d)
- **Objective:** 6-dimensional Hartmann function (standard benchmark)
- **Rationale:** Higher dimensionality, GP needs more trials to converge
- **Bounds:** Known analytic global minimum (-3.32237) and supremum (0.0)
- **Prior design:** Center folklore prior at known optimum, wrong prior at antipodal corner
- **Effort:** ~0.5d (function exists, bounds known, prior straightforward)

**2. Ackley 10D** (replace sampler_proxy_2d)
- **Objective:** 10-dimensional Ackley function (highly multi-modal)
- **Rationale:** Many local optima, GP struggles without guidance
- **Bounds:** Known global minimum (0.0 at origin), bound high from empirical max
- **Prior design:** Center at origin, wrong prior at random off-center location
- **Effort:** ~0.5d (function standard, bounds need empirical check)

**3. Levy 8D** (replace branin_2d)
- **Objective:** 8-dimensional Levy function (multi-modal, ill-conditioned)
- **Rationale:** Non-separable, many local minima, benefits from informed initialization
- **Bounds:** Global minimum known (0.0 at x=[1,1,...,1]), supremum empirical
- **Prior design:** Center at [1,1,...,1], wrong prior at boundary corner
- **Effort:** ~0.5d

**4. Rosenbrock 10D** (alternative)
- **Objective:** 10-dimensional Rosenbrock (narrow curved valley)
- **Rationale:** GP acquisitions struggle with long narrow optimum, prior helps
- **Bounds:** Global minimum 0.0 at [1,1,...,1], supremum empirical
- **Prior design:** Center at optimum, wrong prior off-valley
- **Effort:** ~0.5d

### Effort breakdown (Option B):

| Step | Effort | Description |
|------|--------|-------------|
| Task selection | 0.25d | Choose 2-3 from candidates above, justify dimensionality/modality |
| Implement objectives | 0.5d | Code the functions (most are standard benchmarks) |
| Declare bounds | 0.25d | Run global optimizer to verify minima, empirical max for supremum |
| Design priors | 0.5d | folklore_prior at optimum, wrong_prior well-separated, check support |
| Sanity checks | 0.25d | Verify priors steer correctly, baseline doesn't saturate at n=25 |
| Update v11_tasks.py | 0.25d | Replace task definitions, update registry |
| Re-run pilot | 0.5d | 120 studies (same config, new tasks) |
| Re-size confirmatory | 0.25d | Simulation-based power from new pilot variance |
| **Total** | **2.75d** | Round to 3d with review/iteration buffer |

### Advantages:
- Addresses root cause directly (task difficulty)
- Estimator, pairing, and campaign harness unchanged
- No protocol violation (register sets no minimum task difficulty)
- Likely to show priors helping on hard tasks while remaining safe on wrong priors

### Risks:
- Harder tasks → higher variance → potentially larger required sample size
- If baseline *still* saturates on 6D+ tasks, that's evidence GP+qLogEI is stronger than expected and priors may not be needed (legitimate scientific finding, demote to opt-in per register's demotion rule)

---

## Option E: Escalate to PI

Pause V11 validation pending design review with principal investigator.

### Escalation memo outline:

1. **Finding:** Current task set cannot deliver on V11a's estimand due to baseline saturation
2. **Evidence:** Pilot data (V11_PILOT_REPORT.md), saturation probe showing n=10 already saturated
3. **Options:** Harder tasks (B), reduce budget to n=5 (thin but viable), add noise (artificial), drop V11a (test safety only)
4. **Recommendation:** Option B (harder tasks) for reasons above
5. **Decision requested:** Approve Option B redesign, or redirect to different validation approach

### Effort:
- **Escalation memo:** 0.5d (draft, attach pilot report, prepare decision brief)
- **PI review latency:** Unknown (could be same-day or multi-day depending on availability)
- **Post-decision:** If approved, Option B effort applies; if redirected, depends on new direction

### Advantages:
- Ensures V11 redesign has PI buy-in before committing to confirmatory spend
- Appropriate when pilot uncovers structural issue rather than just noisy estimates

### Risks:
- Delays V11 (blocks priors default-on gate criterion)
- Downstream Tier 1 work not directly blocked (MO veto tests, workloads, other validations can proceed)

---

## Option A: Reduce Trial Budget (Disproved)

Originally recommended n_trials=10 for πBO. Saturation probe disproved this: πBO min headroom at n=10 is +0.0007 (already saturated). Only n=5 leaves meaningful headroom (+0.041), but 5 trials = 1 Sobol + 4 GP proposals, arguably too thin to constitute a meaningful test of the method.

**Status:** Not viable.

---

## Option C: Add Observation Noise (Not Recommended)

Inject Gaussian noise into objective observations (e.g., σ = 0.05 × span).

### Why not recommended:
- Increases variance → inflates required sample size (defeats the purpose)
- Makes tasks feel artificial (acceptance tasks should resemble real HPO, which rarely has 5% i.i.d. Gaussian noise added to deterministic objectives)
- Doesn't address the core issue: tasks are too easy for the baseline, not too noise-free

---

## Option D: V11b Only, Defer V11a (Fallback)

Drop V11a (superiority) from this validation wave. Run V11b (non-inferiority) confirmatory at max_sample=20.

### Rationale:
- V11b's claim ("priors are safe under wrong advice") is testable even with saturation, because we only need to show harm stays above −0.10
- V11a's claim ("priors help under good advice") requires headroom the current setup lacks

### Release consequence (from register):
- V11b pass alone: "Priors are safe but unproven helpful" → opt-in only (not default-on)
- Default-on requires both V11a and V11b pass

### Effort:
- Re-size V11b from pilot: 0.25d
- Run confirmatory: 0.5d (fewer studies than combined)
- **Total:** ~0.75d

### When to consider:
- If PI review (Option E) redirects to "test safety now, defer effectiveness to later wave"
- If timeline pressure prioritizes shipping safe-but-opt-in priors over waiting for full validation

---

## Recommendation

**Pursue Option B (harder tasks) with a 3-day budget.**

**Justification:**
1. Addresses root cause (baseline efficiency on smooth low-dim tasks)
2. No protocol violation (register allows task substitution pre-confirmatory)
3. Moderate risk (variance may increase but unlikely to make campaign infeasible)
4. If redesigned tasks still saturate, that's a legitimate finding: GP is strong enough that priors add little value → demote to opt-in per register's demotion rule (honest outcome)
5. Faster than escalation latency if PI is unavailable, and pilot provides clear evidence for the decision

**Fallback:** If Option B tasks also saturate (unlikely but possible), escalate with both pilot reports and recommend Option D (V11b only, safety-test priors, defer effectiveness claim).

---

## Next Steps (if Option B approved)

1. Select 2–3 replacement tasks from candidates (prioritize Hartmann 6D, Ackley 10D)
2. Implement objectives and verify bounds via global optimizer
3. Design folklore/wrong priors, verify support and separation
4. Run sanity check: no-prior baseline at n=25 should leave >1% headroom
5. Update `validation/v11_tasks.py`, commit with justification
6. Re-run pilot (120 studies, ~18 min)
7. Re-size confirmatory from new pilot variance
8. Proceed to confirmatory if power adequate, escalate if not
