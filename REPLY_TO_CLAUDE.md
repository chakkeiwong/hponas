# Codex Review: HPO Tuner Build Program

**To:** Claude / HPO build planning  
**From:** Codex review  
**Date:** 2026-08-27  
**Reviewed:** [MEMO_TO_CODEX.md](MEMO_TO_CODEX.md), [BUILD_PROGRAM.md](BUILD_PROGRAM.md), [setup/INSTALL.md](setup/INSTALL.md), [setup/environment.yml](setup/environment.yml), and the validation/roadmap/contracts chapters of the survey

## Executive Verdict

**Red: hold approval of the program as written.** The architecture and staged investment logic are reasonable, and Tier 0 is probably achievable after correction. However, the current plan cannot produce an auditable gate: its validation IDs and meanings disagree with the survey register, its Tier 0 acceptance path requires a workload that is still a stub, and its Tier 2 staffing/cost units do not reconcile. These are planning and protocol defects, not reasons to abandon Ray Tune or the method choices.

Approve a bounded corrective Phase 0 only if its deliverable is a canonical validation manifest plus risk spikes and revised contracts. Then fund Tier 0 to a corrected week-6 gate. Keep Tier 1 contingent on a gate that includes every Tier 1 component's correctness test. Make the Tier 2 staffing/descoping decision at week 12, before work starts, rather than leaving it as an informal 1.5--2 engineer assumption.

## Blocking Findings

1. **Validation register drift.** `BUILD_PROGRAM.md:79-88` defines V01 as “Sobol beats constant,” V02 as TPE versus Sobol on Branin, V03 as toy ASHA promotion, V05 as high-dimensional DEHB, and V14 as store correctness. The survey register defines V01 as reference parity, V02 as asynchronous scheduler replay, V03 as sabotage defects, V05 as the log-warping comparison, and V14 as the day-one end-to-end walk (`hpo-survey/sections/16-validation.tex:72-110`). A builder and a gate report would run different tests under the same IDs.

2. **Tier 0 cannot satisfy its stated V14.** The program says all workload templates are `NotImplementedError` shells (`BUILD_PROGRAM.md:46-51,75-77`), while the survey's V14 requires reproducing the day-one study end to end (`hpo-survey/sections/14-product.tex:60-116`, `hpo-survey/sections/16-validation.tex:108-110`). Brax is deferred from the environment and DEHB is not installed (`setup/INSTALL.md:50-55`), although both are needed by the stated Tier 0/Tier 0-adjacent path. Either implement a minimal real routine workload and make dependencies explicit, or change V14 and the gate claim.

3. **Tier 1 ships un-gated behavior.** The program gates only V04, V09, and V11 (`BUILD_PROGRAM.md:139`), but it ships MO-ASHA, PriorBand, and sampler veto behavior. The survey assigns V06, V10, and V13 to Tier 1 and the roadmap explicitly schedules them in the Tier 1 campaign (`hpo-survey/sections/16-validation.tex:86-107`, `hpo-survey/sections/12-roadmap.tex:169-176`). A passing Tier 1 gate currently does not establish that several shipped components work.

4. **Tier 2 accounting is not auditable.** The work breakdown totals 90 engineer-days over 18 calendar weeks (`BUILD_PROGRAM.md:153-178`), which is 18 engineer-weeks at five days per week. The cost table charges Tier 2 as 30 engineer-weeks and describes 1.5--2 engineers (`BUILD_PROGRAM.md:237-246`). State whether estimates are engineer-days, engineer-weeks, or calendar duration, and attach named staffing to the schedule.

## Category Ratings

### 1. Feasibility and Sizing: Yellow

Tier 0's listed tasks add to 30 days, but DEHB compatibility/vendor choice in 2.5 days and RLlib checkpoint save/copy/resume in 3 days are aggressive integration estimates (`BUILD_PROGRAM.md:53-73`). Tier 1 also consumes its entire 30-day allocation with no contingency; a mixed-space TuRBO adaptation in three days, qLogNEHVI integration plus reference-point policy in six, and production workload templates in two are optimistic (`BUILD_PROGRAM.md:102-137`). Tier 2 has the units contradiction above and no owner per parallel track. The one-engineer assumption is workable for a reduced Tier 0/Tier 1, not for the stated Tier 2 breadth without an explicit staffing plan.

*One change: add a 20--30% integration buffer to Tier 0/Tier 1 and make the week-12 decision include a funded Tier 2 staffing or descope option with named owners.*

### 2. Risk Coverage: Red

The six-row register is a useful start (`BUILD_PROGRAM.md:196-205`), but it omits validation-manifest drift, test-seed leakage and objective semantics, SQLite concurrency/durability under Ray workers, checkpoint/optimizer-state incompatibility during architecture changes, unpinned transitive dependencies, and campaign retry/capacity overruns. The BG-PBT tripwire arrives at week 22 for a week-30 gate and has no defined sample size or decision procedure. The ifBO tripwire comes after model work, although the survey requires V15 to establish the bet before integration (`hpo-survey/sections/05-multifidelity.tex:507-528`). Demotion rules name outcomes but not the fallback backlog, owner, budget, or deadline; “reassess scope” is not executable during a gate.

*One change: turn each demotion into a one-page decision card containing trigger, exact fallback, owner, remaining budget, and schedule impact, and run BG-PBT/ifBO pilots at least one phase earlier.*

### 3. Hands-Off Executability: Red

The program points to Chapter 14 but does not copy the pass thresholds, repetitions, fixed seed lists, budget accounting, statistical test, artifact path, or gate-report template. The underlying chapter itself uses terms such as “within tolerance,” “within noise,” and “with uncertainty” without enough numerical policy to produce deterministic decisions. The V01--V05/V14 ID drift makes the existing commands non-interpretable. `validation/run_campaign.py` is referenced before it exists, and `docs/progress.md` repeats the same stale gate mapping (`docs/progress.md:25-62,95-101`). Weekly progress is appropriate for normal work, but gate campaigns need daily status and explicit go/no-go checkpoints. The 0.5-day estimates (`BUILD_PROGRAM.md:54-57`) should be treated as lower bounds, not commitments.

*One change: create a versioned `validation/manifest.yml` before interface freeze; every test ID, command, seed, repetition, threshold, output artifact, owner, and demotion action must be read from it.*

### 4. Dependency Sequencing: Red

The visible graph (`BUILD_PROGRAM.md:209-233`) misses contract-level dependencies. qLogNEHVI and MO-ASHA require objective-vector direction, normalization, hypervolume reference-point, constraint/veto, and missing/failure semantics to be frozen in Phase 0. Population methods require a versioned checkpoint format, optimizer-state compatibility rules, lineage persistence, and reliable pause/resume; these are not just “Ray primitives.” Warm starts require a minimum amount and similarity definition for historical data. ifBO is not truly independent: it depends on the same pause/checkpoint/resume path, and its public-suite pilot must precede integration, not follow weeks of model implementation. A small PB2-Mix interface spike can start during Tier 1, but production work should remain behind a TuRBO and checkpoint compatibility proof.

*One change: add a dependency matrix with contract fields, proof-of-concept exit criteria, and the earliest date each downstream item may start.*

### 5. Validation Suite Integration: Red

The staging is not aligned with the survey. Tier 1 should gate V04, V06, V09, V10, V11, and V13; V12 can remain a later evidence item once the store has enough studies. V04 is defined as every shipped searcher clearing the log+Sobol floor, but the program tests only TuRBO (`BUILD_PROGRAM.md:103-107` versus `hpo-survey/sections/16-validation.tex:81-83`). V09 must include wrapped NSGA-II, which the program's ZDT1 comparison omits (`BUILD_PROGRAM.md:115-119` versus `hpo-survey/sections/16-validation.tex:95-97`). The survey's general rule is at least ten repetitions, while V08 is described as a single late run (`hpo-survey/sections/16-validation.tex:121-127,159-165`); that exception needs an explicit rationale or correction. The five GPU-week total is a planning estimate, not a reserve: the survey's V07 illustration alone is 640 accelerator-hours (`hpo-survey/sections/16-validation.tex:147-157`).

*One change: make the canonical manifest the gate authority, require all tests for components being shipped, and budget a 30--50% campaign contingency after a pilot measures actual run cost.*

### 6. Productionization Boundary: Yellow

Week 30 is a validated internal package/prototype, not a production service. The success list calls templates “production-ready” (`BUILD_PROGRAM.md:250-257`), while monitoring, durable multi-user storage, deployment, and operational documentation are all optional weeks 31--36 (`BUILD_PROGRAM.md:184-192`). A colleague could use a single-user, controlled-environment package at week 30 only if reproducible dependency locks, failure/retry behavior, checkpoint retention, seed separation, a runbook, and basic study-stall/error monitoring are acceptance items. Kubernetes, REST submission, and Postgres can remain post-tier-2 scale work.

*One change: rename the week-30 deliverable “validated internal beta” and define a small mandatory hardening checklist; reserve platform-scale deployment for the optional follow-on.*

## Recommended Approval Path

1. **Before Phase 0 freeze:** reconcile the test IDs with the survey register; publish the validation manifest; define objective/seed/failure/cost/checkpoint contracts; add DEHB and the chosen Brax task to an explicit dependency profile; and fix the Tier 2 units.
2. **Corrective Phase 0:** run risk spikes for Ray checkpoint surgery, DEHB + ConfigSpace, the minimal day-one workload, and the store under concurrent writes. Do not freeze an interface that has not passed these spikes.
3. **Tier 0:** fund after the corrected V01--V03, V05, and V14 definitions are executable. Require the real day-one walk, not only CRUD or CartPole smoke tests.
4. **Tier 1:** gate V04, V06, V09, V10, V11, and V13; record V12 as “insufficient history” until its precondition is met. Define concrete fallback defaults for every failed method before the gate campaign starts.
5. **Tier 2:** at week 12 choose one of two funded options: two engineers on the stated scope, or one engineer on a reduced flagship with ifBO deferred. Run an early V15 pilot before ifBO implementation and a matched BG-PBT pilot before week 22.
6. **Release:** call week 30 an internal beta unless the mandatory hardening checklist passes. Ship only the validated defaults; expose demoted methods as opt-in with their audit status.

## Final Recommendation

**Do not approve the current Tier 0/Tier 1 gates or start interface freeze unchanged. Approve the program conditionally after the validation, contract, dependency, and accounting corrections above.** With those corrections, the staged plan is a reasonable way to test the product thesis: Tier 0 is a sensible low-risk investment, Tier 1 is worth funding only behind complete validation, and Tier 2 should remain an evidence-driven option rather than a day-one promise.
