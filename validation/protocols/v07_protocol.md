# V07 — finite native DEHB conformance

Version 2, prospectively adopted 2026-10-08 under D-DEHB-FINITE. Historical
RL ranking/default rules and contradictory GPU-capacity markdown are preserved
in `archive/program-2026-10-08/before-dehb-finite-migration/manifest.json`.
Neither historical claim is established by this finite contract.

The exact six cases, seeds, options and resource allocation are defined by
`validation.dehb_finite.contract()` and the identical registry entry. Each case
executes 50 native serial DEHB jobs on a rotated quadratic with eigenvalues 1,3.
Each job restarts training at its assigned fidelity (1,2,4,8); every actual
gradient update is charged. Exact eigenbasis powers reconstruct every state
and loss. The minimum full-fidelity loss uses chronological tie-breaking.
Its mathematical optimum is derived by differentiating the degree-16 loss;
regret is descriptive and does not determine a superiority claim.

Original DEHB v0.1.2 commit 58f9fb9045e63530692adc6306fc297e318f11f2
independently reconstructs suggestions, parent/config identities, fidelity and
bracket decisions using retained reports. Native committed and pending JSON
checkpoints must match every declared recovery boundary. No objective or
gradient training is repeated during reconstruction.

PASS requires complete agreement on all fixed cases. Training tolerances are
2e-12 absolute and 2e-10 relative; unit-cube coordinates use 1e-15 absolute
and zero relative tolerance. These are numerical engineering envelopes, not
rigorous floating-point bounds. Violations are FAIL; interruption/missing
generation is INCONCLUSIVE and cannot be replaced. Source/protocol/runtime or
artifact identity failure withholds acceptance. A V16 audit can reproduce a
failure without converting it into a passing scientific result.

Freeze exact source, qualified Python runtime, reference source/dependencies,
protocol, run directory and supervisor before official execution. Allocate
one generation (at most 2,400 gradient updates) and three reconstructions
(zero gradient updates), in two CPU-only processes capped at 300 seconds each.
Use one CPU affinity and one numerical thread; no pilot or power sizing.
Exclusive durable starts consume slots even after interruption. No tolerance
relaxation, favorable selection or human override changes a retained outcome.

## Known Issues

PASS permits only finite opt-in serial native DEHB. Mixed-space encoding is
the HPO-NAS contract, not ConfigSpace equivalence. No asynchronous service,
RL default, optimizer ranking, HEBO upgrade or integrated release follows.
ifBO/V15b remains cancelled under the separate retained non-PASS rule.
