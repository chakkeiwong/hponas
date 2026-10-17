# Optional prior repair and remaining design — PRI-01

Date: 2026-09-28, Asia/Shanghai. **Implementation repair tranche verified; PRI-01 remains incomplete.** Priors stay opt-in. No pilot or confirmatory campaign was launched.

## Executed repairs

The piBO wrapper recreated its Sobol generator on every ask before the first observation, returning duplicate pending configurations. It also serialized only knob names and observations: changed bounds were accepted, while RNG state, acquisition controls and prior identity were omitted. The [before receipt](evidence/2026-09-28/pri-01/before.json) reproduces those defects.

The wrapper now advances one Sobol stream, isolates and checkpoints its CPU torch RNG, and preserves acquisition settings. Schema 2 binds the full space, dependency versions and callable prior recipe, including function source/code identity. Recovery validates all state before replacing the live object; incomplete older snapshots require explicit migration. Unsupported mixed/conditional/logit coordinates and nonfinite observations are rejected instead of silently dropping coordinates or corrupting the GP. Arbitrary callable priors are reconstructed by the caller; checkpoint loading never executes a pickled callable. Exact recovery is verified in the same environment with deterministic priors; cross-version, arbitrary mutable callback and concurrently modified global RNG behavior are not promised.

V11 pilot outputs now remain INCONCLUSIVE even if their numbers clear a significance threshold. The retained portfolio diagnostic spends its exact requested trial count (25 previously became 24 across three artificial rungs). The confirmatory interface refuses the current nonconforming PriorBand method before any spending. Neither `allow_draft` nor selecting only piBO can certify the two-method registered claim. Existing signed-manifest checks are retained for the eventual conforming implementation.

Verification: 48 initial lifecycle/piBO/cost tests passed, 40 harness/manifest tests passed, and 50 final focused tests passed after tightening prior identity. These selections overlap and are not summed. The broad suite explicitly excluding the optional recovery file passed **1,306 tests with 1 documented skip**. The excluded file was separately rerun: **3 passed, 2 failed**. Wrong-prior regret ratio remains 29.257 against <=10; the four-arm spread remains 30,739.248 against <=2. Seeds, budgets, beta, kernel and thresholds were not tuned. Final wheel checks cover the changed modules on Python 3.12 and 3.13. Logs and hashes are bound in [the verification receipt](evidence/2026-09-28/pri-01/verification.json).

## PriorBand reference review

The [paper](https://arxiv.org/html/2306.12370) links to the authors' `automl/mf-prior-exp` repository. At retained commit `fe8632a5ee775ea76fd0fe2d76776d83cef35427`, the experiment configuration uses geometric weights, dynamic incumbent scoring, mutation probability 0.5, mutation standard deviation 0.25, and prior-default evaluation at target fidelity. Its NePS submodule is pinned to **`3f7475b5afaaacdace56f25357ddfbf0e5616157`**. These files, licenses and retrieval hashes are preserved in [the reference manifest](evidence/2026-09-28/pri-01/reference/manifest.json). They were read, not installed or executed.

| Contract | Published mechanism / original source | Current implementation gap |
|---|---|---|
| Rung weights before incumbent activation | Random weight `1/(1+eta**r)`, prior gets the remainder, incumbent zero. With eta=3: prior weights 0.5, 0.75, 0.9. | Fixed random 0.3, prior `0.4*0.9**r`, incumbent gets the remainder. This moves in the opposite direction. |
| Incumbent activation | At least one full-fidelity result and a first-SH-bracket resource threshold. | One scalar observation enables perturbation; no resource/fidelity ledger exists in the sampler. |
| Dynamic mixture | Rank-weighted prior and incumbent densities on top configurations at the highest populated rung; original code uses `max(n//eta, eta)` entries. | No density score comparison; mixture depends only on an artificial rung counter. |
| Local mutation | Each coordinate chosen with probability 0.5, normalized perturbation standard deviation 0.25 in the declared parameter distribution. | Every continuous coordinate gets clipped raw-space Gaussian noise with default 0.1 range scale. |
| Scheduling and budget | Hyperband/SH bracket state, fidelity, continuation costs and full-fidelity incumbent. | V11 splits an ordinary scalar trial count across labels and evaluates every candidate identically; Study/ASHA does not yet expose the needed sampling state. |
| Prior distribution | Sampling and density of a specified distribution are both needed for dynamic scoring. | A general Python density callable plus finite candidate resampling is not an exact prior distribution interface. |

The latest NePS source at `17ac08aa4e6f275000e82c0d0c34b6db933db477` is also retained for comparison. It uses different top-set and resource-accounting expressions; it cannot silently replace the original paper implementation as the oracle. Existing tests of the shipped heuristic do not establish paper conformance. Some percentile-overlap checks compute a separate percentile for each sample and therefore cannot validate a change in sampling distribution.

## Remaining plan and prerequisite decisions

This is **PRI-01 in the existing master**, not a change of execution direction. Its initial register omitted the design dependencies required by its own completion condition (“faithful ... behavior and preregistered recovery evaluation”). D-PROTOCOL and D-TIERS now explicitly gate its remaining conformance/design work, as they already do related scheduler and Tier 1 obligations. The completed correctness tranche is preserved separately from the unfinished item.

The reviewable proposal is to use the paper-linked original NePS revision as the independent reference, preserve the current heuristic under an explicit compatibility name, and specify:

1. Whether the accepted method is full Hyperband PriorBand or a separately named ensemble-sampler extension on the agreed ASHA contract. Their scheduling and cost claims differ; a renamed heuristic cannot satisfy the registered entry.
2. A prior interface with reproducible sampling and density in the same coordinates, supported space types, default/mode behavior, and checkpoint identity. General density-only callables can remain supported by piBO without pretending finite resampling is exact distribution sampling.
3. Rung/resource ledger, incumbent activation, top-set scoring and mutation semantics tied to the chosen reference; exact fixtures include both sides of each activation boundary, ties, missing/failed reports, replay and resource accounting.
4. Separate method-specific V11a/V11b criteria under the final registered family. Existing pooling of `(task, method)` clusters must not hide one failing method. The two retained Branin failures are development diagnostics, not a substitute for the independent-task normalized NI design.
5. After the method contract is settled: implement against those independent fixtures, refresh affected installed checks, then size and preregister the acceptance study with disjoint pilot/confirmation seeds and a measured compute cap. No optimization of a failing test's seed, beta or threshold is part of this plan.

The portfolio/scheduler/interface choices materially change the shipped method and the claim being certified. They belong to the unresolved D-PROTOCOL/D-TIERS ruling; local test passes cannot settle them. PI certification before campaign spending remains required by `validation/protocols.json`, `policy.open_decisions[D5].procedure`. No certification has been inferred from the general repair authorization.
