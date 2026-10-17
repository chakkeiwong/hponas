# V05: finite self-contained known-answer conformance

**Version:** 4.0, 2026-10-05. Prospective amendment under D-SELF-CONTAINED-VALIDATION.

The specified log/linear coordinates, shared physical initialization and resulting numerical search traces conform on the fixed ridge corpus.

## Fixed scope and mathematical answers

Two ridge cases x two GP coordinate arms x two fixed seeds x sixteen proposals = 128 objective calls, plus eight reference probes. Both arms receive the same five physical configurations before acquisition starts. The prefix formula depends only on seed, index and bounds; it does not use the optimum.

The maintained corpus is `workloads/stylized.py:case_specs`. The independent
oracles are `validation/stylized_reference.py`; derivations are in
`docs/program/STYLIZED_TUNING_DESIGN_2026_10_05.md`. The ridge optimum follows
an exact nonnegative regret identity; quadratic worst-direction error follows
the extreme eigenvalues; filter risk follows the stationary Lyapunov/Riccati
solution; bottleneck error and size follow the rank/SVD bound and complete
width enumeration. These statements apply to the declared equations only.

## Freeze and evidence

`validation/stylized_contract.py` fixes seeds 510501/510502, counts and caps.
`validation/stylized_campaign.py` writes the source/protocol/corpus/method/seed
manifest before objective calls. No sibling checkout, download, GPU, data
service or external model is used. All planned study slots, including failed
or interrupted ones, are retained. Raw trial records bind the physical config,
encoded/decoded coordinates, numerical intermediate outputs, objective, work
units and timings. Method identity is reconstructed by replaying every proposal
from its declared seed and prior observations. Independent analytic formulas
and intermediate-output reconstruction check each numerical result. This is
trusted local chronology and measurement, not remote attestation.

## Objective decision and resources

PASS requires all planned slots and probes, legal coordinates, exact proposal
replay, correct first-tie best-result selection, work accounting and model
outputs within the declared binary64 envelope. The envelope is gamma(4096)
times the documented conditioning/scale factor; these tiny dense operations
are below that rounding-operation allowance. It is a conservative engineering
conformance envelope, not an interval-arithmetic theorem or a search-regret
threshold. Exact rational identities separately validate the analytic optima.

Report each regret curve and final selection against its known optimum in its
own units. Do not average different units or gate on a favored method winning.
An observed implementation failure is FAIL; missing completion is INCONCLUSIVE;
changed or malformed identities, hashes or summaries are integrity rejections.
No failed slot can be replaced, and no supplied PASS field determines a verdict.
No statistical alpha, power, pilot, human success threshold or confirmation
sample calculation applies to this finite correctness claim.

One CPU thread; no GPU. Generation is capped at 180 seconds;
each of the two independent decision reconstructions has the same cap. Caps
include acquisition work and Python overhead; timer delivery/OS scheduling are
not a physical hard-real-time guarantee. Raw work and measured wall time are
reported separately. The existing continuous repair authorization covers this
bounded local verification. Run via `python -m validation.run_validation_with_audit V05`.

## Release consequence and prospective retirement

Finite correctness obligation satisfied. Does not promote a searcher or transform to a performance-backed default. All other current-source gates and requirement dispositions remain mandatory. Failure or incomplete evidence blocks
this gate. Exposed cases and two seeds cannot support a population ranking,
a universal log-warping advantage or default promotion. Existing APIs remain
available; caller-declared transforms express modeling choices.

The v3.7 PPO superiority, protected-policy evaluation, pilot/sizing and
allocation requirements are retired for this entry. They are preserved in
`archive/program-2026-10-05/before-stylized-protocol-migration/` and historical
artifacts. No old INCONCLUSIVE/FAIL becomes PASS. Later statistical protocols
retain their own error/power/resource obligations pending explicit review.

## Known Issues

Finite conformance establishes only the declared corpus and equations. GP trace
replay is an implementation-identity check, not an independent optimality proof.
The GP finite-width loss in the development prototype is retained; legal finite
domain acquisition has a separate regression. Continuous stochastic searches
need not attain an exact real-valued optimum in sixteen calls. The SVD fixture
isolates architecture selection and does not certify finite-budget nonlinear
training. Source changes make earlier campaign receipts stale until revalidated.
