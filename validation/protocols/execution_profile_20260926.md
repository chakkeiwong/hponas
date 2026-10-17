# Execution profile — 2026-09-26 repair

This profile describes the repaired runner's conservative interpretation of the existing build-program exit. It does not certify the DRAFT protocol register or change statistical thresholds. Historical protocol snapshots remain intact.

| Gate | Current executable evidence | Historical conflict and treatment |
|---|---|---|
| V01 | SciPy Sobol, independent Optuna and BoTorch runs | All three required. Five Sobol dimensions × 1,000 samples, 30 GP/TPE trials; existing KS fallback thresholds retained. A KS pass does not establish a stronger TOST claim. |
| V02 | GP 20, ASHA 30, crash at 25 of 50, four-worker concurrency, adversarial ordering and empty-log rejection | Suggestions and semantic searcher/scheduler state match exactly. Wall-clock durations are recorded, not required to match independently executed runs. Study canonicalizes completion arrival into dispatch order. |
| V03 | Full individual mutmut inventory, fresh execution, module and critical-path vetoes | `mutmut results --all true`; uncovered mutants remain in the denominator; no static pre-kills. Fresh runs use a separate source copy and never delete historical evidence. Expanded scope includes Study, storage, events, encoding, persistence and adapters. |
| V04-T0 | 5 seeds × 50 evaluations per arm | The markdown specifies a synthetic proxy but also makes proxy-only evidence INCONCLUSIVE. The repaired runner requires real PPO before certification. This strict interpretation does not certify old proxy results. |
| V05 | Real PPO, 3 seeds × 50 evaluations per arm, 100K target training steps | The markdown identifies real RL; the register identifies log warping. Log warping is separately labeled diagnostic and cannot satisfy this gate. |
| V14 | Real bounded PPO, SQLite ledger, policy reload and separate protected evaluation | Protected seed 999 and 60-second ceiling retained. This is an integration demonstration, not a real-workload performance claim. |
| V16 | Recompute decisions; hash source, results, protocol and artifacts | Source inspections and supplied `passed` fields cannot certify execution. A valid FAIL/INCONCLUSIVE artifact may pass audit while the program gate stays closed. |

For the V04-T0/V05 family, each campaign currently uses the sufficient conservative condition p < 0.025 (Bonferroni for m=2), along with the existing ≥5% relative improvement. This cannot admit a result that fails Holm at family alpha 0.05. It may withhold a result that Holm would admit. Relative differences use the absolute baseline mean to support negative returns; a zero baseline is INCONCLUSIVE. Three observations per arm have a minimum exact one-sided Mann–Whitney p of 0.05 without ties, so the current three-seed V05 design cannot pass the sufficient condition. The protocol's allowed larger-seed design requires preregistration and power justification before a confirmatory campaign; this repair does not silently expand it or manufacture power evidence.

PPO configuration mapping fixes `num_envs=32` and 32 minibatches for the full baseline campaign so every integer batch-size candidate in [64,512] is executable. Brax rounds the requested training steps to its update size. Actual steps and full training curves are preserved. Search evaluation seeds are training seed + 100,000; protected acceptance runs are separate and never sent to `observe`.

Tier 1/2 source-review gates are blocked until their conflicting identities and complete campaign evidence are reconciled. V06/V09 scripts remain diagnostic: measured wall-clock costs, actual equivalence intervals, fixed common comparison budgets, and conservative family correction improve correctness but do not replace the hierarchical acceptance protocols. V11 confirmatory execution requires a certified register and a manifest matching source, tasks, seeds, methods and budget. Ed25519 signatures are verified when supplied; trusted signer identity/key custody remains a certification responsibility.

The next V03 execution has a six-hour wall-clock limit, matching the CI job ceiling. mutmut's individual CPU-time limits do not bound workers blocked on a lock. A wall-limited run preserves its partial inventory and is INCONCLUSIVE; the cutoff never converts a mutant into a kill or changes the 90%/20% criteria. The long diagnostic run completed on 2026-09-27 predates this limit.

Canonical GP proposals use one torch CPU thread while fitting and optimizing, then restore the caller's thread setting. Seeded RNG state alone did not ensure exact replay across hosts using different parallel reduction orders. V02 still compares proposals exactly; its tolerance is unchanged.

## Known Issues

The full statistical real-workload and expanded mutation gates may remain FAIL, BLOCKED or INCONCLUSIVE after code repairs. No status in this profile is a claim that the program has exited Tier 0. Historical protocol identity conflicts and power requirements remain acceptance work. GPU/multi-node operations, neural transport, TuRBO, BG-PBT and ifBO remain outside this implementation repair.
