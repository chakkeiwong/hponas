# Memo: HPO Tuner Build Program Review Request

**To:** Codex review  
**From:** HPO build planning  
**Date:** 2026-08-26  
**Subject:** Review of three-tier build program for workspace HPO tuner

---

## Context

We completed a 106-page survey and product proposal for a workspace-internal hyperparameter tuning system (document: `/tmp/sv/main.pdf`, now ready for colleague review). The proposal answers two questions — whether Ray Tune is the right base, and which algorithms to build — and requests two decisions: approve tier-0 build to the week-6 gate, and contingent on pass, approve tier-1 build to the week-12 gate.

The build program translates the survey's Chapter 15 roadmap into executable phases with work breakdowns, gate criteria, demotion rules, and a dependency graph. **This memo requests codex review of the program for feasibility, risk coverage, and hands-off executability.**

---

## What we're asking you to review

**Three documents in `/home/ubuntu/workspace/hponas/`:**

1. **`setup/INSTALL.md` and `setup/environment.yml`** — environment setup, dependency rationale, verification steps
2. **`BUILD_PROGRAM.md`** — the phased build plan with work breakdowns, gates, and risk register
3. **This memo** — framing and specific review questions

**The survey itself** (context, not a review target): `/tmp/sv/main.pdf` holds the evidence base, decision boxes, and validation suite specification (Chapters 11–15 are the product proposal; the rest is methods teaching).

---

## Program structure summary

**Three tiers, three gates:**

- **Tier 0 (weeks 3–6):** Wrap audited components (Ray ASHA, Optuna TPE, DEHB), wire the run store, deliver the routine-budget floor. **Gate:** V01–V03, V05, V14 pass.
- **Tier 1 (weeks 7–12):** Build the method differentiators (trust-region BO, prior-aware qLogEI, qLogNEHVI, MO-ASHA, PriorBand, warm-start). **Gate:** V04, V09, V11 pass.
- **Tier 2 (weeks 13–30):** Build the flagship (PB2-Mix, BG-PBT) and the frontier bet (ifBO curve model). **Gate:** V07, V08, V15 pass, full suite clean.

**Budget:** 42 engineer-weeks implementation + 5 GPU-weeks validation campaigns. **Risk discipline:** Every load-bearing method has a pre-committed demotion rule tied to a numbered validation test; alternatives are named.

**Approval requested:**
1. Tier 0 to week-6 gate (~6 weeks, low risk, wrapping only)
2. Contingent on gate pass: tier 1 to week-12 gate (~6 weeks, first method builds)

---

## Specific review questions

### 1. Feasibility and sizing

- **Are the work breakdowns realistic?** E.g., "Trust-region BO: 7 days" assumes adapting BoTorch TuRBO to our schema is ~3 days of code. Is that aggressive, or padded?
- **Is the one-engineer-through-tier-1 assumption viable?** Tier 0 and tier 1 are each scoped at 30 eng-days (6 weeks). Does the sequencing allow one person to work linearly, or are there hidden parallelization needs?
- **Tier 2 scope check:** 30 eng-weeks over 18 calendar weeks suggests 1.5–2 engineers or extended timeline. The program says "suggests scaling or timeline extension" but doesn't commit. Should we force that decision now, or leave it to the week-12 gate outcome?

### 2. Risk coverage

- **Are the tripwires early enough?** E.g., "Week 22: if BG-PBT informal tests show <50% win rate, flag early" for a week-30 gate. Is 8 weeks of lead time sufficient to pivot, or should we pilot earlier?
- **Missing risks?** The register covers method failures, dependency issues, and gate cost overruns. What's not listed that could derail a tier?
- **Demotion rules: clear enough?** E.g., "qLogNEHVI failure → demote to tier-2 option, Hamiltonian study defaults to scalarization." Does that give the week-12 decision-maker enough to act on, or does it need a fallback work plan written now?

### 3. Hands-off executability

- **Can someone execute tier 0 from `BUILD_PROGRAM.md` without asking clarifying questions?** The breakdown goes to 0.5-day granularity in places ("Sobol/Random: 0.5d"). Is that helpful specificity, or false precision?
- **Gate criteria: operationalized enough?** E.g., "V04 (TuRBO beats Sobol)" — the validation chapter (Ch14 of the survey) defines "beats" as statistical significance via Mann-Whitney U at α=0.05 over 20 replications. Does the program need to restate that, or is pointing to Ch14 sufficient?
- **What's the right cadence for progress tracking?** The program says "update `docs/progress.md` weekly." Is that too frequent (overhead), too infrequent (drift undetected), or about right?

### 4. Dependency sequencing

- **Critical path:** TuRBO (tier 1) → PB2-Mix (tier 2A) → BG-PBT (tier 2B) is 16 weeks and load-bearing. ifBO (tier 2C) runs in parallel (5 weeks). Is this serialization necessary, or could we start PB2-Mix design during tier 1 to compress the critical path?
- **Hidden dependencies?** The program shows the method dependencies (BG-PBT needs TuRBO, MO-ASHA needs qLogNEHVI). Are there infrastructure dependencies we're missing? E.g., does the warm-start engine (tier 1) need the store to hold a certain amount of history, which means we can't validate it until after tier 0 has logged enough trials?

### 5. Validation suite integration

- **Is the three-gate staging correct?** Tier 0 gate runs V01–V05, V14 (6 of 15 tests). Tier 1 gate adds V04, V09, V11 (9 total). Tier 2 gate runs the full V01–V15. Are we leaving any "should have caught this earlier" tests to tier 2 that would save cost if run at tier 1?
- **Campaign cost realism:** The budget line says 5 GPU-weeks of campaigns total. Chapter 14 of the survey estimates 0.5 + 1.5 + 3 = 5 GPU-weeks, which matches. But those are pre-sizing estimates. Should we add a 50% contingency buffer, or is 5 GPU-weeks already conservative?

### 6. Productionization boundary

- **Is the tier-2 deliverable production-ready, or prototype-ready?** The program describes post-tier-2 work (weeks 31–36) as "optional hardening" — Kubernetes setup, API server, Postgres migration, monitoring. If a colleague wants to use the tuner at week 30, can they? Or is tier 2 "validates the methods but not the service"?
- **Internal-use vs external-package:** The survey's Chapter 11 says "workspace-internal tool, not a general-purpose package." Does that mean we skip post-tier-2 entirely and ship tier 2 as-is, or does "internal" still need monitoring/alerting to be usable?

---

## What we're NOT asking you to review

1. **The method choices themselves** — whether BG-PBT is the right flagship, whether qLogNEHVI is worth building — those are argued in the survey's decision boxes, not re-litigated here. The program takes the survey's verdicts as given.
2. **The validation suite design** — test definitions, statistical protocol, sabotage entries — those are specified in survey Chapter 14. The program references them, doesn't redefine them.
3. **The survey's teaching quality** — that's for the colleague review the survey is now entering. The program assumes the survey's evidence base is sound.

**Navigation note:** Survey chapters are numbered in reading order (Ch1–15), but the source files retain the authoring order (`14-product.tex` = Ch11, `12-roadmap.tex` = Ch15). All references in this memo and the build program use chapter numbers. If you're opening LaTeX source, see [hpo-survey/main.tex](hpo-survey/main.tex) lines 80–84 for the include order.

---

## How to use your review

**Near-term (this week):** Your feedback gates whether we start Phase 0 (weeks 1–2, interface freeze). If the program has blocking issues — unrealistic sizing, missing risks, unclear decision rules — we fix those before touching code.

**Medium-term (week 6 and week 12):** Your review of the gate criteria and demotion rules will be the template we use to write the gate reports. If a gate fails, we'll reference the demotion rule you reviewed here.

**Long-term (week 30):** The tier-2 scope question (one engineer extended timeline, or two engineers on schedule, or descope) doesn't need an answer today, but your input on whether that's a week-12 decision or a day-one decision helps us sequence stakeholder conversations.

---

## Specific review format request

For each of the six question categories above, we'd find it useful to get:

1. **A risk rating:** Green (looks reasonable, no blockers), Yellow (concerns but not blocking, or needs clarification), Red (blocking issue, must fix before starting).
2. **Specific callouts:** Line items in the program that are under-scoped, over-scoped, or missing a contingency.
3. **One-sentence advice:** If you were executing this, what's the one thing you'd change?

**Example response format:**
> **1. Feasibility and sizing: Yellow**  
> TuRBO adaptation at 3 days feels aggressive if mixed-space kernels need custom logic; budget 5 days. Tier-2 scaling decision should be forced at week 12, not left ambiguous. Otherwise sizing looks reasonable for a senior-level builder.  
> *One change: Add 20% time buffer to tier 1 (6 weeks → 7 weeks) to absorb integration surprises.*

---

## Logistics

- **Documents to review:** `hponas/BUILD_PROGRAM.md` (main), `hponas/setup/INSTALL.md` (environment), `hponas/setup/environment.yml` (dependencies), this memo
- **Survey for context (optional):** `/tmp/sv/main.pdf` — read Ch11 (product), Ch14 (validation suite), Ch15 (the roadmap this program operationalizes) if you want the evidence layer
- **Timeline:** We'd like to start Phase 0 (interface freeze) this week if the program is sound, so review by end-of-week is helpful but not binding

---

## Why this matters

The survey's policy discipline (evidence-backed verdicts, falsification clauses, demotion rules) only works if the build program enforces it. If we write "BG-PBT demotes on V08 failure" but then don't run V08 until it's too late to pivot, the policy was theater. Your review is the check that the program's gates, breakdowns, and risk register are actually load-bearing.

Thanks for the review. Questions or need more context, just ask.

---

**Attachments (paths):**
- `/home/ubuntu/workspace/hponas/BUILD_PROGRAM.md`
- `/home/ubuntu/workspace/hponas/setup/INSTALL.md`
- `/home/ubuntu/workspace/hponas/setup/environment.yml`
- `/tmp/sv/main.pdf` (survey, context only)
