# V02 Protocol: recorded event and runtime conformance

**Version:** 2.0
**Date:** 2026-09-30
**Status:** Exact finite input and assertion inventory frozen before execution
**Tier:** 0; deterministic veto, no inferential alpha

## Claim and scope

Scheduler decisions and runtime recovery conform to the adopted specification
on the complete declared recorded-event corpus. Replay alone is insufficient.
This implements the registered state-machine/property correction and the
master's SPEC-02/SPEC-03 requirements. Finite checks do not prove correctness
under every possible asynchronous schedule or crash point.

The prior protocol and candidate evidence are archived. Schema-1 results remain
engineering diagnostics, even if their producer reports PASS. The global
protocol register remains DRAFT where other identities or prerequisites remain
unresolved; a V02 PASS cannot release the product by itself.

## Prospective freeze

Before executing the first scenario or assertion, freeze current source/tests,
Python/dependency versions, both protocol files, original event population bytes,
reference sources, all eight scenario recipes, the exact collected node IDs of
all thirteen mandatory conformance files, their source hashes, PASHA fixture
bytes, Hypothesis seed 9202930 and the 600-second CPU execution cap.

The fixed 10,000-case stratum is
`docs/program/evidence/2026-09-29/stat-03/v02-proposed-population.json`, whose
original digest is retained by `validation.v02_contract`. No regeneration from
favorable outputs, dropped cases or post-execution subset is permitted.
Its ASHA bottom-rung grammar covers arrival, duplicate, conflicting, dropped,
late-terminal and checkpoint cases. Independent pinned promotion source supplies
the reference; this stratum alone does not cover all scheduler behavior.

`validation.v02_conformance.FILES` declares the complete additional inventory:
ASHA/median and PASHA independent references; checkpoint and scheduler contracts;
local/Ray streamed runtime; report lifecycle, promotion, progressive cap, state
recovery, study checkpoint, streamed reporting and replay. Collection is checked
again during verification. Every planned setup, assertion and teardown must
complete. Skips and expected failures are not acceptance evidence. Assertion
counts without the frozen code, fixture and individual outcomes are insufficient.

## Eight raw scenarios

1. GP replay: seed 42, 20 suggestions, exact replay and independent vendor history.
2. ASHA replay: seed 43, 30 roots, rungs 1/3/9, exact scheduler/state replay.
3. Crash recovery: seed 44, 50 roots; real process exit code 73 while root 25 is
   pending after 25 committed completions; resume all 50 without reexecuting
   committed work. Raw journals, checkpoints and polynomial outcomes are checked.
4. Concurrent recovery: seed 45, 20 roots, four Ray worker processes; both forward
   and reverse completion orders with independently verified overlapping worker
   intervals, exact NumPy suggestions, polynomial scores and final state.
5. Adversarial events: both delayed arrival orders, duplicate/stale reports and
   single promotion checked against the fixed reference outcomes.
6. Non-vacuity: empty replay is rejected.
7. Streamed replay: seed 47, two roots, resume at rungs 1/2/4, total recorded
   resource 8, exact terminal/replay state.
8. Cancelled replay: seed 48, one root, interruption before the objective tail,
   recorded resource 2, cancellation and exact replay state.

Raw scores/configurations are checked against the mathematical fixture and
independent NumPy/BoTorch procedures, in addition to replayed state checks.
PASHA conformance uses the disclosed deterministic unordered-pair adapter where
specified, not an undisclosed claim about the unmodified vendor epsilon.

## Decision and resources

PASS requires zero discrepancies, complete original case inventory, all eight
raw scenarios and all mandatory assertion phases passing. Any discrepancy or
failed assertion yields FAIL, including when other cases are missing. Missing
execution, skipped checks, resource exhaustion or incomplete journals without an
observed discrepancy yield INCONCLUSIVE. Invalid identities/hashes/chronology
fail integrity and cannot certify a result. Human acceptance cannot override it.

The CPU cap is 600 seconds for scenario and conformance execution. Collection
and independent verification are reported separately from that execution cap.
The suite runs only within the remaining cap; a scenario may overshoot and that
overshoot vetoes PASS. Failures/timeouts remain preserved without retry-until-pass.
No PPO training or GPU campaign is part of this deterministic fixture.

Run with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m
validation.run_validation_with_audit V02`. Schema-2 raw results, frozen contracts,
worker artifacts, individual pytest-phase journal and process log are write-once
within a new run. Source changes invalidate the current freeze. Local process
and monotonic-time records describe trusted-host instrumentation, not externally
authenticated chronology. V16 independently recomputes the finite decision;
release still requires every master dependency and the other acceptance gates.

## Known Issues

Coverage is finite: the bottom-rung grammar alone does not cover later promotion, median or PASHA transitions. The mandatory broader suite is therefore part of the frozen inventory. Local journals and process timing assume a trusted host and do not authenticate remote chronology. No performance or universal asynchronous correctness claim follows from these fixtures.
