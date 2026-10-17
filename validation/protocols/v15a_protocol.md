# V15a — finite original pretrained ifBO feasibility

Version 2.0, prospectively adopted 2026-10-08. The exact contract is
`validation.ifbo_finite_contract.contract()`, identical to the registry.
The derivation, resource allocation and complete reference boundary are in
`docs/program/evidence/2026-10-08/tier3-feasibility-01/finite-plan.md`.
Both conflicting historical V15 designs remain in
`archive/program-2026-10-08/before-ifbo-finite-feasibility/manifest.json`.

Use the original ICML source and original published checkpoint, without training
or surrogate substitution. Six fixed initial-coordinate/seed pairs each use
24 resumable matrix-gradient updates followed by eight charged certification
updates for the recommendation. ASHA receives the same physical work. The
quadratic spectral dynamics and global optimum have closed-form references.
Raw logits, candidates, probabilities, every state/update and final selection
are retained. Independent algebra reconstructs training, PI and ASHA decisions;
separate exact source replay checks pretrained method identity.

PASS requires all six pointwise certification-loss gaps no greater than zero
within the fixed float64 envelope (2e-12 absolute, 2e-10 relative), plus source,
weights, roster and conformance. PI uses a 5e-6 float32 engineering envelope.
A finite shortfall is FAIL; missing/interrupted work is INCONCLUSIVE. Neither
human acceptance nor a supplied PASS label can override the raw calculation.
FAIL/INCONCLUSIVE cancels owned integration and V15b without a favorable rerun.
Only PASS permits a separately frozen V15b exact finite integration-parity phase.

Before data freeze qualified source/runtime, external source and harness hashes,
run name and protocol/registry. Allocate one generation and exactly three durable
reconstructions, in two supervised processes capped at 300 seconds each (600
seconds total), one CPU affinity and numerical thread, no GPU. All starts
consume their slots even after interruption. Maximum physical updates including
all replays: 1536. V16 reconstructs the verdict independently of stored labels.

## Known Issues

The bounded harness executes unchanged upstream numerical component bodies with
an explicit continuous-space adapter, manual initialization of used attributes,
a captured CSV writer, and the removed Torch Optional annotation alias restored.
It does not reproduce the historical full benchmark stack/runtime. A distinct
neutral development case ([2,3], seed 7) checks harness reconstruction and is not
in the official six-case roster. Earlier main-branch prediction smoke used a
different checkpoint; it remains separate exposed development evidence.
These engineering envelopes do not prove roundoff bounds. This finite result
cannot establish posterior calibration, general optimizer effectiveness,
wall-clock efficiency, a default or integrated release. No pilot or power
calculation applies to this expressly finite claim.
