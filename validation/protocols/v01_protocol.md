# V01 Protocol: finite reference trace conformance

**Version:** 2.1
**Date:** 2026-10-01
**Status:** Authorized scope; exact inputs frozen before each acceptance execution
**Tier:** 0

## Claim and authorization

Every component in the declared V01 inventory conforms to its explicitly named
reference on the frozen finite tabular and event corpus, under the bound source,
dependencies, numerical settings and random streams. This is a finite conformance
observation, not equality in distribution, universal transition equivalence or
scientific performance superiority.

D-V01-REFERENCE-SCOPE records the user's authorization of
`docs/program/V01_SCOPE_AMENDMENT_PROPOSAL_2026_09_30.md`. The immutable scope
receipt binds that proposal. Authorization changes the claim; it cannot decide
its result. The old protocol and evidence remain archived. The global protocol
register remains DRAFT for other unresolved claims.

D-V01-COVERAGE-SCOPE additionally adopts the exact reviewed
`docs/program/V01_DATA_COVERAGE_PROPOSAL_2026_09_30.md`. Its scope receipt records
the user's instruction to continue after the two scope proposals were presented.
The original v1 run remains INCONCLUSIVE. This amendment changes the coverage
claim: known original missing cases test truthful refusal; an added complete
domain tests the affected components' full trajectories. It recovers no rewards.

## Objective decision

- **PASS:** Every required complete trajectory executes fully; each frozen
  expected-missing case agrees exactly with the independently reconstructed
  reference through its named source cell and stops there. All 45 cases execute
  and every required observable agrees. Missing refusals are not complete
  trajectories.
- **FAIL:** Any reconstructed observable discrepancy, including one on an
  incomplete trajectory. FAIL takes precedence over missing evidence.
- **INCONCLUSIVE:** Unexpected missing source cells, missing execution/evidence,
  execution error or exhausted resource cap, without an observed discrepancy.

Broken identities, changed sources, invalid recipes or corrupted artifacts fail
integrity verification and cannot certify a result. There is no partial PASS,
score imputation, favorable task replacement, post-outcome subset or
rerun-until-pass. KS non-rejection, TOST, numerical tolerance bands, alpha and
power do not establish this finite exact claim. Human acceptance cannot override
any result. Historical schema-1 diagnostics cannot certify this protocol.

## Frozen inventory and corpus

`validation/designs/v01_finite_corpus_v2.json` binds the four retained original
ARLBench PPO tables: Ant, HalfCheetah, Hopper and Humanoid. Known missing cells
remain included. This is an exposed development regression corpus, not held-out
or randomly sampled evidence. No population inference is made.

For each table: optimizer seed 23; recorded table seed 0; Random, Sobol, TPE and
CMA-ES each request 12 evaluations, GP requests 6, LegacyGP requests 3, all at the
maximum recorded fidelity. ASHA, Median and PASHA each request 30 roots and use
all recorded fidelities. The complete Cartesian product contains 36 cases in
the frozen order. All 36 original cases remain. The nine HalfCheetah cases
declare their exact original first-missing cells, independently checked against
the source and reconstructed references. The other 27 must complete.

Nine added cases use the same component/count/seed recipe on **all 187** seed-0
HalfCheetah configurations finite at **every** original fidelity. The remaining
69 incomplete configurations are excluded only from this added domain. No score
ranking, return threshold, alternate seed or favorable trajectory defines
membership. The verifier reconstructs membership and exact CSV bytes from the
original source. Projection geometry differs on this domain and is explicit.
These nine trajectories must complete; no missing exception applies to them.
The frozen inventory therefore has 45 cases: 36 complete-trajectory obligations
and nine exact refusal obligations. The original corpus and missing-case
evidence are hash-bound and cannot be dropped or reclassified. The register's
general maximum of 30 optimizer seeds does not permit changing the current
authorized seed 23 recipe.

The nine exact reference identities are:

| Component | Reference |
|---|---|
| Random | NumPy RandomState uniform stream |
| Sobol | SciPy scrambled Sobol stream |
| TPE | Optuna TPESampler |
| CMA-ES | Optuna CmaEsSampler |
| GP | BoTorch dimension-scaled Matern-5/2, qLogEI |
| LegacyGP | BoTorch gamma-prior Matern-5/2, seeded qLogEI |
| ASHA | Pinned Syne Tune 0.13.0 promotion source |
| Median | Independent completed-reference running-mean specification |
| PASHA | Pinned Syne Tune 0.13.0 with sorted-set unordered-pair adapter |

PASHA's deterministic pair correction is explicitly part of its reference. This
is not parity with unmodified vendor epsilon behavior. Original vendor source,
adapter and counterexample remain available. Each scheduler generates its own
one-worker dispatch stream, with promotions before new roots; there is no claim
covering every asynchronous event order.

## Observations and reconstruction

Both actors independently propose configurations, query the original recorded
cells and update their own state. Common projection uses normalized coordinates,
log learning rate, nearest recorded configuration and lowest configuration ID
for projection ties. No return is interpolated.

Acceptance compares exact projected configuration cells, statuses, recorded
scores, incumbent selections with earliest-observation tie breaking, scheduler
dispatches/decisions, resource milestones, and PASHA cap/epsilon. Incumbents are
tracked separately at each recorded fidelity; final selection uses only the
maximum fidelity. Recorded training steps describe the table recipe, not measured
training time. Continuous proposal differences are retained diagnostics; no
post-hoc floating-point tolerance determines acceptance.

The verifier reconstructs each vendor's whole adaptive path from its seed and
the original table, without invoking the tested wrapper. It reconstructs scores,
incumbents and resource observations from raw rows. Producer verdicts and summary
flags are never the oracle. Missing cells halt that actor immediately and remain
visible. A matching prefix satisfies only an explicitly frozen missing-refusal
obligation, never a complete-trajectory obligation. Unknown missingness cannot
be reclassified after execution.

## Execution and evidence

`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m validation.run_validation_with_audit V01` writes a new immutable run.
Before any case executes, it freezes the complete inventory, exact table bytes,
protocol register and individual protocol, authorization, current source digest,
dependency versions, reference sources/adapter and CPU double-precision,
one-thread numerical recipe. Local monotonic execution records bind that freeze
to every ordered case and its raw evidence. These are instrumentation on a trusted
local host, not hostile-host authentication or independently anchored chronology.

The corpus permits at most 600 seconds of local CPU case execution. The cap is
checked between cases; a running case may overshoot. Any overshoot is recorded
and vetoes PASS. All skipped/error case slots remain in the result. No PPO
training or GPU allocation is authorized by this protocol.

Schema-2 evidence uses exact path/hash bindings, source/dependency checks and an
independently recomputed decision. An audit of an INCONCLUSIVE campaign is an
integrity observation, not scientific acceptance. A V01 result alone does not
close the master, its dependency gates or the overall release.

## Known Issues

The retained HalfCheetah table contains blank cells whose causes are unknown.
They stop nine original trajectories, whose v1 result remains INCONCLUSIVE.
The v2 gate tests their exact refusal and adds full trajectories on a disclosed
derived domain. This exposed finite corpus cannot establish population
equivalence or continuation beyond missing outcomes. PASHA uses the disclosed
corrected reference adapter. Local timing and process records assume a trusted
host; measured training runtime is absent from the source tables.
