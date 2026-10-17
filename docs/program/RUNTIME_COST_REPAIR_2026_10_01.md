# Allocated measurements and scientific resource control

This review is part of the existing master, within STAT-03 / STAT-03P and
VAL-01. It supersedes the previous review's current GPU-occupancy blocker.
The original refusal, every earlier timeout and the prior review remain
unchanged. All 93 requirements, 30 work items and 19 protocol identities remain
in the program. No scientific campaign or release has been accepted or allocated.

## Completed fixed measurements

GPU3 was free at the new preflight and before each planned profile. All six
fixed recipes completed on the repaired workload and explicit CUDA runtime.
Their child wall times total 1,174.214 seconds (19.57 minutes), within the
2,160-second plan. These are point measurements, not uniform runtime bounds.

| Recipe | Search seconds | Separate evaluation seconds | Full child seconds |
|---|---:|---:|---:|
| Ant, batch 64 | 93.662 | 30.597 | 128.627 |
| Ant, batch 512 | 139.509 | 29.842 | 173.793 |
| HalfCheetah, batch 64 | 158.921 | 38.976 | 202.506 |
| HalfCheetah, batch 512 | 256.542 | 39.821 | 301.032 |
| Hopper, batch 64 | 118.730 | 29.467 | 152.979 |
| Hopper, batch 512 | 181.294 | 29.081 | 215.277 |

The independent review checks every profile artifact hash, planned recipe,
source identity, occupancy observation, episode count and actual learning-curve
step count. All ten separate evaluation returns in each profile are finite.
The complete result does not replace any historical failure.

Brax rounds the requested training budget to whole updates. With four epochs,
an update contains `batch_size * 10 * 32` transitions. The exact count is
`4 * update * ceil(100000 / (4 * update))`: 163,840 steps at batch 64 and
655,360 at batch 512. Across the integer domain, the smallest resulting count
is 101,120 at batch 79. The task names describe the requested 100k recipe;
they must not be read as exactly 100,000 transitions or equal actual step
counts across configurations. The adopted comparison charges actual elapsed
time. No task recipe has been changed to obtain these measurements.

Three bounded CPU optimizer profiles used one fixed synthetic response surface
and 20 suggestions each. Total suggest/observe times were 6.014 seconds for
log GP, 19.660 for linear GP and .038 for TPE. These establish execution and
observed overhead on that surface; they do not measure PPO effects or bound
optimization/replay cost on arbitrary observed histories.

## Repaired worker limits

The scientific campaign previously passed its entire remaining allocation to
each child. Its later accounting could veto an overlong study, but a stalled
study could consume the remaining campaign window first.

Search children now receive at most the task search budget plus its overshoot
allowance. Protected children receive at most the task policy-evaluation cap.
Both also respect the remaining campaign time. These are whole-child limits,
including interpreter and readiness startup. The process verifier reads the
actual recorded timeout and rejects excessive, absent or nonfinite limits.
Timeouts remain unresolved observations without retries. Termination and
artifact overhead are measured; this does not claim an exact hardware deadline.

The focused worker/runtime suite passed 49 tests; the futility and campaign repair suite passed 64 tests; the integrated validation and governance suite passed 577 tests at that snapshot. A later retained-worker regression repair adds three behavioral cases. Protocols V04-T0/V05 are version 3.7 and the unfrozen candidate is v2.2.5. Fresh V01 and V02 campaigns passed their finite gates and V16 audits before this final source repair; their receipts are now stale and must be refreshed before scientific freeze. The generated master status owns final source freshness.

## Full-study development measurement

Single-training timings omit repeated PPO calls, adaptive GP suggestions,
selected-policy counts and verification of a full trace. The completed bounded
measurement is one Ant GP study on development stream 940. It is
part of this master and uses no pilot or confirmation stream.

Its search budget is six times the largest measured Ant search cost, rounded
up to a minute: 840 seconds. A 240-second overshoot allowance gives a 1,080-second
whole-child timeout. The protected stage has 600 seconds with 60 seconds per
child; the entire coordinator has an 1,800-second launch envelope. All selected
incumbents and interruptions are retained. This is a development measurement,
not a recommendation for the final scientific search budget. An adaptive GP
observation is verified from the resulting trial count, never assumed from
the nominal budget. The exact plan and attempt are under
`evidence/2026-10-01/scope-adoption/full-study-*`.

The bounded search completed nine PPO trials, including four adaptive GP trials, in 899.410 seconds of child search time (907.543 seconds including the child wrapper). Independent trace verification took 2.635 seconds. Three selected policies were frozen for development evaluation. A subsequent evaluation attempt found GPU3 occupied and started zero protected children; the refusal and inventory are retained. The first attempt remains incomplete. The exact three evaluations subsequently completed in attempt 05, with 107.733 successful child seconds and thirty finite returns. Failed startup attempts add 15.872 child seconds. The current scientific-freeze review discloses the historical runtime-guard limitation and the independently reconstructed bindings.

## Pilot cost and the permitted early failure stop

The prior illustrative twenty-search-unit cost scenario, recomputed with the
complete profile set and fresh-process startup, totals 1,899.8 GPU-hours over
828 studies. The current shared per-entry cap representation would reserve
2,533.067 hours across both entries. These are explicit scenario ceilings,
not measured full-study throughput, a required minimum, a recommendation or
permission to spend. In particular, multiplying observed single-call costs
cannot supply the unknown actual workload effects or pilot sizing reliability.

The adopted 46-vector sizing rule requires all 46 vectors to be good. At a
hypothetical good-vector probability .95, sizing succeeds with probability
.95^46 = .094468 per entry. This is not a measured effect or confirmation power.
All claims, margins, error levels, planning confidence and confirmation limits
remain unchanged.

A useful cost control follows exactly from that same rule. If b vectors already
contain irretrievably unresolved search studies, at most m-b pilot vectors can
be good. The Clopper-Pearson lower probability bound is monotone in the good
count, as is every sufficient binomial power tail. If the optimistic completion
with m-b good vectors cannot size, no remaining outcomes can rescue this pilot
under its frozen rule. The first certain-futility bad counts are 1 at m=46,
3 at m=100 and 9 at m=200. This permits an early failure stop, never early
success, changed sample counts, replacement observations or a scientific PASS.

STAT-03P/PILOT-SEARCH-FUTILITY records the implementation and verification work
following the active source-bound measurement. Every unexecuted planned slot
must remain missing, and the independent verifier must reconstruct the reason
for skipping protected work. Confirmation still follows its original fixed-count
rule. This repair does not authorize the full pilot or alter its accepted scope.

## Continuation

The retained evaluations and proven early failure stop are complete. Correct the pilot-specific readiness review, finish the exact conditional resource proposal, and refresh conformance after the final source repairs. Advance independent mutation readiness while pilot allocation is pending. Continue all eligible preparation. A routine phase boundary is not a
stop, and this review does not mark the master or Tier 0 complete.
