# SCI-02 scientific repair companions

These versioned modules have a separate saved-artifact verification envelope.
They are not part of the installed hponas wheel, and do not inherit its core
qualification. The master stage and exact receipts live under
docs/program/evidence/2026-10-25/scientific-gap-repair-02. They import no sibling
repository, data, environment or service. Use the fixed operations documented
in docs/PROGRAM_OPERATIONS.md for the retained one-time verification sequence.

## Interfaces

- pi_float32.probability_of_improvement(logits, borders, incumbent_loss)
  accepts finite float32 logits (rows by bins) and strictly increasing float32
  borders. It reproduces the pinned BarDistribution float32 geometry with
  independent double softmax/summation. The original absolute envelope is
  5e-6. ifbo_reference_v2.verify_case uses this repair while retaining the
  old query, update and recommendation checks. The original validation module
  remains immutable because its failed campaign consumes it. No model is
  loaded or pretrained forward performed; full model identity is not proved.
- nas_certificate.check_certificate(model, paths, seconds=120) checks a
  scalar 2-4-4-1 SiLU model with the saved JSON layer/config schema. Paths form
  a complete binary partition of the fixed rational rectangle, alternating
  splits of x and a. It computes new outward bounds against exp(-x*a) and
  the original derivative limits; it does not trust any recorded bound.
  CERTIFIED proves the stated real-valued mathematical claim.
  NOT_VERIFIED reports an insufficient bound or resource limit, not an
  observed violation. Malformed input raises ValueError. Exact outward upper
  endpoints are retained as mpmath tuples; display floats are not acceptance
  evidence. This verifies a supplied partition; it does not search partitions
  or guarantee other architectures, targets or inference arithmetic.
- exact_references supplies the analytic banana transform/inverse/density,
  Gaussian harmonic flow, a direct quarter-period reference, and bounded
  paired-utility precision formulas. Callers must supply independent Gaussian
  inputs for the probabilistic reference; deterministic values cannot prove
  independence. The wallet formulas require the protocol's independence and
  missingness assumptions and cannot create missing empirical evidence.

## Verified outcomes and remaining limits

All 138 retained ifBO calls match the upstream PI body within the unchanged
envelope; the upstream body reproduces the saved probabilities exactly in the
checked runtime. The independent reconstruction's maximum absolute error is
1.708331662797491e-7. All six ifBO recommendations remain worse than ASHA;
integration remains cancelled.

All 297 leaves for six retained NAS models pass both the companion and the
separate retained flattened-Hessian derivation. The maximum displayed upper
ratio is 0.9976441816737961. Fourteen controls check partitions, model shape,
nonfinite data, unsupported architecture, resource exhaustion and a
noncompliant zero network. No training or new seed evaluation occurred.

The exact transport proof is limited to the named synthetic target. The wallet
protocol freezes three selected/baseline pairs and six prospective comparisons,
with pairwise regret bounds and fixed/sequential uncertainty rules. No new
observations were collected, and utility superiority remains unresolved.

Promoting these companions into the installed product or a future live
validation campaign needs separately reviewed integration and affected-source
qualification. No historic campaign verdict changes as a result of these tools.
