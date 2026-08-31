# Memo: Statistical Protocol Review Request

**To:** Codex review  
**From:** HPO governance implementation  
**Date:** 2026-08-29  
**Subject:** Review of validation statistical protocols (deferred R0 item)

---

## Context

During Phase R0 (specification correction), we applied 8 statistical corrections to the validation protocols in Chapter 16 of the survey ([hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex)). These corrections define the methodology for validation campaigns that gate tier progression.

**Status:** R0 marked this item as "deferred, non-blocking" with the rationale that the reviewer validates finished protocols rather than deriving them, and that validation lead execution would provide an empirical check. The deferral window (R1 weeks 1-2) has closed without the review occurring.

**Current situation:** Tier 0 implementation is underway. The validation protocols become load-bearing at the Tier 0 gate (8-10 weeks from now), when ~2,500 accelerator-hours of campaign compute runs against these specifications.

**This memo requests Codex review of the 8 statistical corrections for internal consistency, adherence to standard practice, and operational clarity.**

---

## What we're asking you to review

**Primary document:**
- [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex) — validation chapter with the 8 corrections applied

**Supporting context:**
- [R0_COMPLETION_REPORT.md](R0_COMPLETION_REPORT.md) — lists the 8 corrections with line ranges
- [BUILD_PROGRAM_v2.md](BUILD_PROGRAM_v2.md) — validation register showing which entries run at which gates

**The 8 corrections (from R0):**

| # | Correction | Lines in 16-validation.tex |
|---|-----------|---------------------------|
| 1 | Non-inferiority margins (δ=5% for V06, δ=10% for V11); "inconclusive" as distinct outcome | 184-198 |
| 2 | Repetition count from pilot variance at 80% power; "inconclusive at budgeted precision" is a verdict | 127-157 |
| 3 | New subsection: sampling levels, pseudoreplication, paired designs, hierarchical bootstrap | 240-272 |
| 4 | New subsection: development vs acceptance tasks, versioned rotation | 274-298 |
| 5 | New subsection: primary endpoint per entry, Holm–Bonferroni for secondary, descriptive exempt | 300-327 |
| 6 | V06 cost in actual accelerator-seconds incl. startup/checkpoint/queue; full-run-equiv secondary | 200-216 |
| 7 | New subsection: immutable signed manifests, `validation/artifacts/` not gitignored | 329-356 |
| 8 | V08 release semantics: demote/hold/pass; Tier 2 completion accepts "hold" | 409-439 |

---

## Why this matters

**Cost of wrong protocols:**
- **Wrong margins** (correction #1): Pass a method that shouldn't ship, or fail one that should
- **Wrong power** (correction #2): "Inconclusive" verdict after burning campaign budget
- **Wrong cost model** (correction #6): V06 claims about scheduler overhead don't match reality
- **Wrong multiple-comparisons correction** (correction #5): Type I error inflation or power loss

**Empirical backstop:** Correction #2 explicitly calls for pilot campaigns to set repetition counts from observed variance. This catches some errors (sample size too small) but not others (wrong margin choice, wrong endpoint).

**No named reviewer:** R0 sequenced this as "non-blocking, overlaps R1 wks 1-2" but no reviewer was assigned and the window closed. We're now ~8 weeks from first campaign execution.

---

## Specific review questions

### 1. Non-inferiority margins (correction #1)

**Lines 184-198 in 16-validation.tex**

The protocols specify:
- V06 (early stopping nearly free): δ=5% quality loss threshold
- V11 (priors help under good advice): δ=10% recovery threshold
- Three-outcome logic: win / inconclusive / fail

**Questions:**
- Are these margins defensible for their domains? V06 tests on RL tasks where between-seed noise is ~10-15%; V11 tests recovery after wrong prior injection.
- Is the three-outcome logic (win/inconclusive/fail) correctly specified? Should "inconclusive" trigger a replication with more budget, or is it a terminal verdict?
- Does the margin choice interact with the power calculation (correction #2)?

**Risk if wrong:** V06 passes ASHA even though quality loss exceeds what users would tolerate, or fails ASHA due to noise when true loss is acceptable.

### 2. Power and sample size (correction #2)

**Lines 127-157 in 16-validation.tex**

The protocol specifies:
- Run pilot (e.g., 3 reps per arm)
- Compute effect size and between-arm variance from pilot
- Set final repetition count to achieve 80% power at α=0.05
- If budgeted precision cannot reach 80% power, report "inconclusive at budgeted precision"

**Questions:**
- Is 80% power the right target for validation tests whose failure triggers demotion or tier-block decisions?
- Is α=0.05 appropriate, or should multiple-comparisons correction (Holm-Bonferroni per correction #5) change this?
- Is the "inconclusive at budgeted precision" verdict operationally clear? Does it mean "defer decision," "demote by default," or "escalate for more budget"?
- Does the pilot-to-final sizing procedure correctly account for variance estimation error in the pilot itself?

**Risk if wrong:** Campaigns sized at 10 reps when 20 are needed → "inconclusive" verdict after burning budget, tier progression blocked, no actionable information gained.

### 3. Hierarchical bootstrap and pseudoreplication (correction #3)

**Lines 240-272 in 16-validation.tex**

The protocol specifies:
- Sampling levels: seed-level (between independent runs) vs within-seed variation
- Paired designs where applicable (same seed across arms)
- Hierarchical bootstrap: resample runs, then resample trials within runs
- Fallback to unpaired if seed-level correlation breaks

**Questions:**
- Is the hierarchical bootstrap procedure correctly specified? Should we resample with replacement at both levels, or stratified at the run level?
- Is the paired-vs-unpaired decision rule clear? What "breaks" seed-level correlation — different convergence rates, different trial budgets, or something else?
- Does this procedure correctly handle the RL domain's structure (10-20 trials per seed, ~10 seeds per arm)?

**Risk if wrong:** Pseudoreplication inflates significance; paired tests claim differences that vanish when properly analyzed; or paired tests lose power by ignoring legitimate correlations.

### 4. Development vs acceptance tasks (correction #4)

**Lines 274-298 in 16-validation.tex**

The protocol specifies:
- Development tasks: Used for prototyping, visible to method builders during implementation
- Acceptance tasks: Held out, versioned rotation (V04a uses task set A, V04b uses B)
- Primary claims tested on acceptance tasks; development tasks are descriptive

**Questions:**
- Is the rotation mechanism clear? Does "versioned" mean we archive the seed set when the gate runs, or that we pre-commit seeds before starting the tier?
- Should development tasks be entirely separate environments (e.g., CartPole for dev, Brax for acceptance), or same environment with different seeds?
- Is there a risk of overfitting to acceptance tasks if they're reused across tiers (e.g., V04 at Tier 0, V04 again at Tier 1)?

**Risk if wrong:** Methods tuned to development tasks fail in production; or acceptance tasks leak into development, invalidating the validation.

### 5. Multiple comparisons correction (correction #5)

**Lines 300-327 in 16-validation.tex**

The protocol specifies:
- One primary endpoint per validation entry (specified in register)
- Holm-Bonferroni correction for families of secondary endpoints
- Descriptive analyses exempt (no decision impact)

**Questions:**
- Is Holm-Bonferroni the right correction for our structure? We have 15 validation entries, but they run at different gates (6 at Tier 0, +3 at Tier 1, +6 at Tier 2). Should correction be per-gate or across the full suite?
- Is the primary-vs-secondary split correctly applied? E.g., V04 tests "beats log+Sobol floor" as primary; should anytime performance (quality at 50% budget) be secondary with correction, or descriptive?
- What happens if a secondary endpoint fails but primary passes — does the method ship with a documented limitation, or does secondary failure trigger demotion?

**Risk if wrong:** Type I error inflation (claim differences that are noise) or power loss (correct for 15 comparisons when 6 are load-bearing).

### 6. V06 cost accounting (correction #6)

**Lines 200-216 in 16-validation.tex**

V06 tests "early stopping is nearly free" by comparing searcher+ASHA (stops trials early) vs searcher-at-full-fidelity (runs all trials to completion). The protocol specifies:
- Cost measured in actual accelerator-seconds (wall-clock on GPU)
- Includes trial execution + startup + checkpoint + queue time
- Secondary endpoint: "full-run-equivalent" budget (if ASHA runs 100 trials to 1/3 budget, that's 33 full-run-equivalent)

**Questions:**
- Is wall-clock the right metric, or should we use GPU-seconds (excluding queue/idle)? V06's claim is about user-facing cost, which includes queue.
- Is the full-run-equivalent secondary correctly defined? Should it normalize by final quality reached, or just by compute spent?
- Does this cost model handle variable-duration trials correctly? (e.g., RL trials that terminate early on success)

**Risk if wrong:** V06 passes by claiming ASHA is cheap when queue overhead dominates (not a scheduler win), or fails by charging ASHA for startup costs that full-fidelity also pays.

### 7. Artifact immutability (correction #7)

**Lines 329-356 in 16-validation.tex**

The protocol specifies:
- Signed manifests (SHA256 hash) for all validation artifacts
- `validation/artifacts/` directory tracked in git (not gitignored)
- Manifest includes: code version, hyperparameters, seed list, result file hash

**Questions:**
- Is SHA256 sufficient for integrity, or should we use a full signing scheme (GPG)?
- Does the manifest capture enough context to reproduce? Should it include dependency versions (numpy, jax, Ray)?
- How do we handle artifacts that are too large for git (e.g., 10GB checkpoint files)? Should those live in git-lfs, S3 with manifest, or git-ignored with manual archival?

**Risk if wrong:** Validation results claimed but not reproducible; gate report references artifacts that later change; regression testing breaks when old baselines are lost.

### 8. V08 release semantics (correction #8)

**Lines 409-439 in 16-validation.tex**

V08 tests "population line does not lose in its home regime" (BG-PBT vs DEHB/BO+ASHA above 8 workers). The protocol specifies three outcomes:
- **Pass:** BG-PBT wins or ties on both sides of 8-worker threshold
- **Hold:** Promising but needs more evidence; tier 2 completes, ship deferred pending follow-up
- **Demote:** BG-PBT loses; demote to option, default to DEHB

The protocol also says Tier 2 completion accepts "hold" as non-blocking.

**Questions:**
- Is the three-outcome logic operationally clear? What evidence distinguishes "hold" from "demote"?
- If V08 returns "hold," what's the follow-up plan? Who funds it, and what's the deadline?
- Should "hold" block internal beta launch, or is it acceptable to ship with BG-PBT as opt-in during the hold period?
- Is this outcome model generalizable to other entries (e.g., should V09, V15 also have hold outcomes), or is it specific to V08's flagship status?

**Risk if wrong:** V08 returns "hold," tier 2 completes, no one funds follow-up, BG-PBT ships untested, or gets demoted by default after 6 months of drift.

---

## What we're NOT asking you to review

1. **Method choices** — whether BG-PBT is the right flagship, whether qLogNEHVI is worth building — those are in the survey's decision boxes and were covered in your prior review (B2, B6).
2. **Implementation feasibility** — whether 8 days for TuRBO is realistic — that's in BUILD_PROGRAM_v2 work breakdown, not a statistical question.
3. **Empirical parameter choices** — whether δ=5% is the right margin can only be settled after pilots run and we see actual noise levels. We're asking whether the protocol correctly specifies *how* to use pilot data to make that determination.

---

## Review format request

For each of the 8 questions above, please provide:

1. **Risk rating:** Green (protocol is sound), Yellow (concerns but not blocking, or needs clarification), Red (error or ambiguity that will cause campaign failure or invalid results)
2. **Specific issue (if Yellow/Red):** What's wrong or unclear
3. **Suggested fix (if Red):** What should the protocol say instead

**Example response:**

> **2. Power and sample size: Yellow**  
> The "inconclusive at budgeted precision" verdict is operationally ambiguous — does it mean defer, demote, or escalate? Recommend adding a decision tree: if pilot shows effect size >2x margin but variance is high, escalate for more budget; if effect size <margin, demote; if effect size ~margin, defer and note uncertainty in gate report.  
> The pilot-to-final sizing procedure doesn't account for variance estimation error. Recommend Boos & Hughes-Oliver (2000) method: size for 80% power at estimated effect ±1 SE, which adds ~15-20% reps.

---

## Why Codex review is appropriate here

**Text-verifiable portion:** Whether the protocols are internally consistent (e.g., does Holm-Bonferroni application match the primary/secondary split), whether they follow standard practice (e.g., hierarchical bootstrap for nested designs), and whether the decision rules are operationally clear (e.g., "hold" vs "demote" distinction). This is a document review task well-suited to LLM capability.

**Empirical portion:** Whether δ=5% is the right margin, whether 10 reps will have enough power — these depend on actual noise levels and can only be settled by pilots. The protocol correctly defers these to pilots (correction #2), so text review validates the *procedure* for using pilot data, not the final numbers.

**Limitations of this review:**
- You are not a credentialed statistician; if the concern is "we need external expert sign-off for scientific credibility," this review doesn't provide that.
- Subtle numeric errors in power calculations (e.g., wrong degrees of freedom in t-test) are harder for LLMs to catch than logic errors (e.g., "you applied correction to the wrong family").
- False assurance risk: A "GREEN" rating should not be logged as "external statistical review complete" — it's a substantive first-pass review, and the empirical pilot check remains necessary.

**Recommendation if you flag RED findings:** Escalate to a human statistician (academic, ML benchmarking background) for a 1-week paid review before Tier 0 gate.

---

## Timeline and usage

**Near-term (this week):** Your review informs whether we proceed to Tier 0 gate (weeks 8-10) with current protocols, revise them now, or escalate to human statistician.

**Medium-term (week 8-10, Tier 0 gate):** Validation lead will self-certify protocols as part of gate prep (correction #2 requires pilots anyway). Your review provides a prior check before campaigns run.

**Long-term (post-campaign):** If a validation entry returns "inconclusive" or reveals a protocol error mid-campaign, we'll reference your review when diagnosing whether the issue was foreseeable.

---

## Logistics

**Documents to review:**
- [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex) — lines 127-439 contain the 8 corrections
- [R0_COMPLETION_REPORT.md](R0_COMPLETION_REPORT.md) — context on what each correction fixed
- [BUILD_PROGRAM_v2.md](BUILD_PROGRAM_v2.md) — validation register (which entries run at which gates)

**References cited in the protocols:**
- Eimer et al. (2023) — HPO benchmarking best practices (lines 158-162 in tex)
- Bouthillier et al. (2021) — accounting for variability in DL (line 243 reference)

**Timeline:** Review by end-of-week preferred (Tier 0 gate is 8 weeks out, but campaign setup starts sooner). Not blocking — if this takes 2 weeks, that's fine.

---

## Summary: What's at stake

The prior Codex review (B1-B10) caught scope mismatches, timeline errors, and missing test layers before any code was written. That review saved weeks of rework. This statistical review is narrower — it's 8 specific protocol sections, not a full program — but the cost of error is similar: wrong protocols → invalid campaigns → tier blocked or wrong decision at gate.

We're asking you to do what you do well (text-level logic review, standard practice check, operational clarity) on a load-bearing document before it runs against 2,500 accelerator-hours of compute.

Thanks for the review. Questions or need more context, ping us.

---

**Attachments (paths):**
- [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex)
- [R0_COMPLETION_REPORT.md](R0_COMPLETION_REPORT.md)
- [BUILD_PROGRAM_v2.md](BUILD_PROGRAM_v2.md)
- [RESPONSE_TO_CODEX_REVIEW.md](RESPONSE_TO_CODEX_REVIEW.md) — prior review for context
