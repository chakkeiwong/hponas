# Repair plan and execution record — 2026-09-26
**Program integration:** This is the RPR-01 execution record under [the current master](../CONSOLIDATED_MASTER_AUTHORITY.md). Open acceptance work is tracked in [the structured work register](program/program.json); the September 27 results below remain immutable historical evidence when source changes.

Starting point: commit `9904089` and the [2026-09-25 audit](audits/2026-09-25-codebase-gap-audit.md). Authorization: user requested a repair plan, thorough review, and execution. Preserve the audit/cache evidence and existing gate thresholds.

## Reviewed scope and design

Repair defects in existing components and the path to the stated Tier 0 goal. Do not implement the separately deferred TuRBO/BG-PBT/ifBO/distributed-service roadmap as incidental fixes. A repaired validator may correctly report FAIL, BLOCKED or INCONCLUSIVE; implementation completion and certified performance are separate acceptance milestones.

1. **Evidence and gate integrity (A01, V03, A11).** Read all mutmut statuses with the installed supported CLI; enforce module scores, critical survivors, and reviewed exclusions. Require campaign evidence and provenance at the gate. Remove registry fake passes. Restore compilation and require manifests for confirmatory campaigns. Test negative artifacts and missing evidence before accepting positive ones.
2. **Public contracts and recovery (A02–A08, A10).** Use the Knob space as the public schema with a compatibility adapter for Parameter spaces. Keep existing import paths. Make GP objective direction/kernel explicit; share space encoding across baseline/GP paths. Make observations idempotent. Give Study a persistent, atomic checkpoint ledger, actual remaining-budget resume, asynchronous batch execution, and ordered replay. Enforce executor limits and restore scheduler configuration.
3. **Existing algorithm/workload correctness (A09, T01–T06).** Correct minimized MO acquisition inputs, exclusive HV contributions, batch cost sums, RNG state, scalarization, categorical TPE, model construction, and sampler diagnostics. Separate protected evaluation from optimization and produce actual model artifacts. Keep workload smoke checks explicitly distinct from confirmatory RL claims.
4. **Validation and review.** Turn audit counterexamples into regression checks; run affected suites, then the available broad suite, clean package build/install, maintained examples and gate negative checks. Review the final diff for compatibility, crash boundaries, cost accounting, side effects and accidental weakening of thresholds. Record campaign limitations rather than manufacturing gate passes.

## Review decisions before implementation

- Preserve both existing APIs through adapters; avoid deleting legacy modules while callers still depend on them.
- Checkpoint before dispatch and after observation; resume pending configurations without asking the searcher again. No repeated completed trials, and every incumbent must resolve to its original configuration.
- Batch completions are observed in dispatch order for deterministic replay; concurrency width is part of the checkpoint contract. Scheduler promotion events are distinct from new search configurations.
- Local hard deadlines require an isolated process that can be terminated; a thread timeout alone leaves computation running. Do not fork an initialized GPU runtime.
- Failed/retried work must contribute to reported cost; queue wait and measured objective time must have explicit semantics.
- Unknown or stale validation schemas fail closed. Historical artifacts are retained as historical; gates require current source/protocol fingerprints.
- Protocol identity conflicts remain visible. Tier 0 requires the explicit build-program IDs; V05 real-workload acceptance cannot be satisfied by the differently named log-warping experiment. No threshold changes based on observed repair results.
- Unit/regression tests establish behavior, not real-workload statistical superiority. Long campaigns may still fail after implementation defects are repaired.

## Execution checklist

- [x] Evidence/gate integrity and negative tests
- [x] Public API, mixed spaces and GP objective/kernel behavior
- [x] Study persistence, resume, execution and replay
- [x] Scheduler identity/state and executor limits
- [x] Existing MO/cost/TPE/sampler defects
- [x] Real model/workload artifacts and protected evaluation
- [x] Packaging, documentation and CI
- [x] Broad verification and final review

These checkboxes record implementation work. They do not assert that the corresponding statistical or mutation gates passed.

## Implemented repairs

| Audit finding | Implemented behavior | Verification and limits |
|---|---|---|
| A01: false passes and inconsistent gates | Tier 0 requires V01/V02/V03/V04-T0/V05/V14 and their V16 receipts. Decisions are recomputed from individual observations, with source, protocol, result and dependent-artifact hashes. Unknown, empty and stale evidence cannot certify a gate. Later-tier source-only gates stay blocked. | Negative artifact and forged-PASS regressions. Historical protocol conflicts are documented in the execution profile; this is not a certified replacement register. |
| V03 accounting | Use mutmut 3.8 `results --all true`; include uncovered mutants in the denominator; apply per-module, critical-survivor, timeout and equivalent-review vetoes. Execute in a new source copy and preserve old caches. | Retained 2,287-mutant evidence disproves the reset memo's zero-kill diagnosis. The expanded fresh campaign is recorded separately below. No static pre-kills or relaxed threshold. |
| A02/A04: public composition and mixed spaces | Export the actual API; use Knob/SearchSpace as the canonical schema; adapt Parameter spaces and legacy searchers. Share log/logit, categorical, ordinal and conditional encoding. | Public Study regression and installed-wheel mixed-space GP example, including the model-based phase. Mixed GP encoding is a numeric relaxation, not a claim of advanced categorical-kernel support. |
| A03: GP direction and kernel | Apply minimization sign before fitting/acquisition; construct Matérn 5/2 explicitly; isolate torch RNG effects. | Sign/kernel interception, replay after warmup, independent BoTorch parity. |
| A05–A07: resume, observation identity and replay | Atomic schema-2 snapshots contain trial configurations, completed results, pending work, searcher/scheduler state and dispatch events. SQLite commits ledger and query views together. Observe last result per canonical trial ID; replay typed events in dispatch order, including empty promotion rounds. | Completed runs dispatch no new work; actual process termination/resume reproduces the uninterrupted trace; changed/empty event logs fail. Pending work may rerun after a crash; external objective effects need trial-ID idempotency. |
| A08: scheduler/executor controls | Restore scheduler configuration and RNG state; replace repeated rung reports; prevent duplicate promotions; use bounded local workers and isolated processes for hard deadlines. Ray bounds submissions, retries infrastructure failures and charges failed-attempt elapsed time. | Local deadline/side-effect regression; external Ray retry, failure, cost and concurrency tests. Ray's automatic internal retries are disabled so they cannot hide attempts from the executor ledger. |
| A09: real models and protected evaluation | Width/depth/activation build actual networks. Brax PPO uses these coordinates and saves policy parameters, recipe and learning curve. Search evaluation uses separate seeds; protected acceptance is a later checkpoint evaluation and is never observed by the searcher. | V14 executes real bounded CPU PPO, SQLite persistence and policy reload. This demonstrates composition, not full-budget RL superiority. |
| A10: installation and CI | Explicit package discovery/extras, compatible dependency ranges and tested Brax Git pin; compile/lint and test jobs; mutation job propagates failure and uploads evidence. Default pytest discovery excludes the retained mutation cache. Audited database/checkpoint evidence is eligible for version control. | Wheel build, isolated target installation and public optimization/resume smoke. Dependencies came from the recorded working environment; no claim of a fresh dependency-resolved environment on every supported platform. |
| A11: V11 campaign/manifest | Restore executable campaign; require source/task/seed/method/budget manifest checks; verify Ed25519 signatures when present. | Compilation and tamper rejection. Trusted signer identity and a registered confirmatory campaign remain certification work. |
| T01–T05: MO/cost/TPE | Negate minimized MO outcomes/reference for BoTorch; use exclusive hypervolume contributions; restore MO RNG positions; sum batch costs before applying temperature; freeze scalarization reference and align objective direction; restore categorical/pending TPE state. | Mathematical counterexamples and continuation checks, plus affected searcher/scheduler suites. V06/V09 remain diagnostic pending the declared hierarchical real-workload campaigns. |
| T06: sampler diagnostics | Autocorrelation-aware rank/split ESS and R-hat reject stuck/degenerate chains. Describe the implemented workload as ordinary HMC. | Independent versus autocorrelated/stuck-chain regressions. Learned neural transport remains unimplemented. |

## Final review additions — 2026-09-27

The optional πBO acquisition added log-prior values but detached Python prior calls from torch gradients. This let direct acquisition-value tests pass while local optimization ignored the prior's slope. A bounded finite-difference derivative for the log prior now combines with the analytical GP gradient. A known quadratic optimization problem moves from 0.2 to the correct weighted optimum 0.5; a separate check covers log coordinates, batches and boundaries. The prior decay formula and statistical thresholds are unchanged. Discontinuous priors still present the usual limitations of local optimization.

The external worker-crash test exposed a second layer of Ray retries that was invisible to the executor's accounting. Disabling that layer makes the configured retry limit and failed-attempt cost authoritative. All 25 focused Ray tests pass, including an actual worker process crash and successful retry.

The broad suite exposed a simultaneous-first-open SQLite race: `PRAGMA journal_mode=WAL` could raise `database is locked` immediately. Store now retries that idempotent transition with a bounded wait and closes the connection if initialization fails. The existing concurrency test now checks every worker future and closes its connections. A separate stress probe opened 50 fresh databases with four writers and 20 writes each: 1,000 writes completed without lost rows or exceptions. The affected recovery/scale/regression selection passed 37 tests; Store-specific checks passed 14 with 7 existing skips.

Mutation reporting now preserves the executed snapshot's fingerprint even when the live source changes during a long run. Such evidence remains INCONCLUSIVE for the current source. Hypothesis's `differing_executors` health check is suppressed for the property suite because mutmut invokes it in multiple workers; all property assertions remain active.

The long mutation diagnostic completed naturally before an attempted interrupt reached it. Its complete 4,469-mutant inventory contains 2,862 kills, 579 survivors, 605 timeouts, 341 uncovered mutants and 82 abnormal exits. Score: **2,862 / (4,469 − 605) = 74.07%**; timeout rate: **13.54%**. Ten of 18 modules miss 90%, and 133 critical-path survivors remain. The source changed during execution, so the stored current-source verdict is INCONCLUSIVE even though the snapshot's score/veto analysis fails. No equivalent exclusions were applied. The preserved workspace is `/tmp/hponas-v03-kwd6pgd8`; future runs also have a six-hour wall-clock limit and retain partial evidence on expiry.

The final gate review found that GP proposals could differ by about 2×10⁻⁹ when a campaign ran with two torch CPU threads and was replayed with the host's default 128 threads. GP suggestion calls now serialize changes to their torch runtime settings, use one CPU thread during fitting/acquisition, and restore the caller's thread count and CPU RNG state. The independent vendor comparison uses the same numerical setting. The exact replay comparison is unchanged. Fresh V01/V02/V14 campaigns passed, and the normal gate command reproduced V02 at the host default thread count. This establishes reproducibility in the recorded environment, not across arbitrary hardware or dependency versions.

## Final verification — 2026-09-27

The [evidence index](audits/evidence/2026-09-27-repair/README.md) and [verification receipt](audits/evidence/2026-09-27-repair/verification.json) preserve test results, campaign paths, dependency versions, source fingerprint and wheel hash. The final review covered the public/legacy boundaries, checkpoint identity and crash behavior, replay, executor retry/cost semantics, protected evaluation, installation, and rejection of stale or misleading evidence. Existing acceptance thresholds were retained.

| Check | Result | Qualification |
|---|---|---|
| Broad suite: `pytest tests --ignore=tests/test_prior_recovery_pibo.py -q` | **896 passed, 18 skipped** | The excluded file was executed separately; its failures are below. |
| Optional πBO recovery suite | **3 passed, 2 failed** | Wrong-prior and four-arm recovery assertions remain failing; no xfail or threshold change. |
| Final repair/evidence regressions | **31 passed** | Includes mutation deadline preservation and exact GP proposals across caller thread counts. Included in the broad suite. |
| Focused external Ray checks | **25 passed** | Includes real worker crash/retry accounting; these do not establish mutation coverage. |
| SQLite first-open stress | **1,000 writes passed** | 50 fresh databases, four concurrent writers, 20 writes each. |
| Ruff, compilation and diff whitespace | **Passed** | Maintained source/tool/workload/example trees; historical mutation copies are excluded. |
| Final wheel build and installation | **Passed** | Eight-trial mixed/conditional/log-space GP study and Store resume from an isolated install target; no repeated completed work. Uses existing dependencies. |

The 18 skips include seven empty Store conformance placeholders and several stale scheduler/API skips. Concrete Store/concurrency/crash regressions run elsewhere, but skipped placeholders do not establish corrupted-database recovery or backup guarantees. They remain a test-coverage gap.

| Required campaign | Final gate status | Evidence interpretation |
|---|---|---|
| V01 | **MET** | Independent GP/Sobol/TPE vendor comparisons; V16 PASS. |
| V02 | **MET** | Replay, crash/resume, concurrency and adverse events; recomputed exact replay and V16 PASS. |
| V03 | **BLOCKED** | Prior repair snapshot diagnostic imported with its original receipt; INCONCLUSIVE for final source. The snapshot itself fails mutation acceptance. |
| V04-T0 | **BLOCKED** | Real PPO smoke execution only; INCONCLUSIVE with V16 PASS. |
| V05 | **BLOCKED** | Real PPO smoke execution only; INCONCLUSIVE with V16 PASS and unresolved design/identity issues. |
| V14 | **MET** | Actual bounded PPO, saved policy, persistence, resume and separate protected evaluation; V16 PASS. |

All six artifact sets passed V16 integrity checks. V16 accepting an INCONCLUSIVE diagnostic is not a performance or mutation PASS. The [final Tier 0 gate](../gate_reports/tier0_gate_2026-09-27.md), run without a thread-count override, exits 1 with three criteria met and three blocked. **Tier 0 certification has not been achieved.**

## Acceptance work still open

1. **V03:** strengthen behavior coverage and review survivors from the expanded population, especially Study, Store, adapters, schedulers and executor control paths. The mutation selection currently excludes live Ray test files; those tests pass externally but do not contribute to the mutation score. Bring their control-path checks into a mutation-compatible test selection before the next frozen run. Meet every module threshold and the zero-critical-survivor veto; do not infer a pass from aggregate kills.
2. **V04-T0/V05:** reconcile the stable claim/ID and register the full real PPO design before claiming certification. Five- and three-seed baseline runners exist, but the three-seed exact Mann–Whitney minimum p-value is 0.05; it cannot satisfy the current p<0.025 family condition. Use the protocol's preregistration/power route for a larger design. Smoke execution cannot repair this statistical design defect or certify performance.
3. **Optional πBO/V11:** the corrected acquisition still fails the unchanged recovery assertions: wrong-prior regret ratio **29.257 > 10** at 50 trials, and four-arm relative spread **30,739.248 > 2** at 30 trials. These are real failing assertions, retained without xfail, threshold changes or altered seed/budget selection. The four-arm statistic divides by the best arm's regret and needs a preregistered treatment of near-zero regret before being used as a reliable acceptance statistic. Optional-prior performance remains uncertified.
4. **Later tiers:** execute the registered MO/cost/warm-start/sampler campaigns and resolve their ID drift. TuRBO, BG-PBT, ifBO, learned transport and distributed service operations remain separately deferred roadmap work.

No Git reset, cache deletion, commit or publication is part of this repair. Tier 0 certification remains open until verified current artifacts satisfy every required gate.
