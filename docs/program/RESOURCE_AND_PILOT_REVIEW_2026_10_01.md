# Runtime repair, pilot feasibility and the next allocation

This is revision 1.21 of the existing master, within STAT-03 / STAT-03P and
VAL-01. It does not change the accepted scientific claims, margins, error rates,
power target, confirmation cap or later-tier obligations. The whole-program
review retains all 93 requirements, 30 work items and 19 protocol identities.

## Repairs and objective evidence

The prospective joint-event sizing rule is implemented and checked against exact
rational integration and binomial confidence coverage. It uses one frozen
method before pilot outcomes. Forty-six ideal pilot vectors per entry are the
first feasible count, replacing the old sufficient counts 277/131. This means
828 task/arm studies before confirmation; none has been allocated or executed.
The preserved original five-vector reservation remains a futile historical plan.

The current v2.2.3 candidate reserves 46 pilot vectors in spaced groups under
the existing twenty-slot task offsets. All 258 task/phase/vector namespaces are
distinct; original reserved initialization configurations are unchanged. The
preparation evaluated no objectives. All three named development-exposed tasks
and the existing statistical assumptions remain binding. The exact scope receipt
is technically rebound under the existing authorization, without a new approval.

The small pilot is fragile: all 46 vectors must be jointly good. If the unknown
probability of a good vector were .95, the chance that this pilot sizes a
confirmation is only .95^46 = .094468 per entry. At .99 it is .629824. These are
conditional operating characteristics, not measured PPO effects or confirmation
power. An ideal minimum is not a recommendation to run a large campaign.

Evaluation now batches the independently seeded episodes and retains individual
terminal stopping, terminal rewards, horizons and genuine nonfinite failures.
Six behavioral tests include different stopping times within the same batch.
On the retained HalfCheetah checkpoint and the same ten episode keys, the
successful batching experiment took 46.209 seconds inside evaluation, versus
111.789 seconds in the earlier serial profile. All returns were finite; the
maximum absolute return difference was .158703. Compilation and shared-host
conditions changed, so there is no exact numerical compatibility or controlled
speedup claim. Fresh scientific data must use the repaired frozen source.

The first batching experiment failed during CUDA library loading and showed
memory contention. An explicit installed CUDA13 library directory and .20
memory fraction fixed the experiment. Both attempts are retained. Runtime
identity now binds the interpreter, single GPU UUID/device kind, CUDA library
paths, backend and memory fraction. Parent readiness, child bootstrap, actual
worker backend and independent process reconstruction enforce that identity;
phase resource resizing cannot change it. Forty-one focused runtime/phase/process
tests passed before the final candidate/register reconciliation.

## Measured resource boundary

These are fixed development recipes and seeds, not full HPO studies or uniform
runtime bounds over the searched domain. Each timeout remains in its original
directory. The original six jobs had separate 180-second caps; the three
follow-ups had separate 360-second caps.

| Recipe | Original workflow seconds | Follow-up workflow seconds |
|---|---:|---:|
| Ant, batch 64 | 124.529, complete | — |
| Ant, batch 512 | 173.230, complete | — |
| HalfCheetah, batch 64 | 180.610, timeout | 347.011, complete |
| HalfCheetah, batch 512 | 180.663, timeout | 360.637, timeout |
| Hopper, batch 64 | 140.099, complete | — |
| Hopper, batch 512 | 180.882, timeout | 199.046, complete |

The serial HalfCheetah batch-512 follow-up completed search in 325.181 seconds
but not the separate evaluation within its cap. The final production-batching
workflow completed search in 346.319 seconds under contention, then exhausted
its 360-second cap during separate evaluation. It does not demonstrate complete
final-workflow timing or a slower/faster controlled comparison.

The cost ledger reconstructs every recorded observation and gives an explicit
illustrative planning scenario. Twenty repetitions of the largest observed
single-search cost set search allowances; 1.5 times observed costs, rounded up
to a minute, set overshoot/policy allowances; up to 50 distinct protected
incumbents and a minute per study for process/artifact handling are charged.
This scenario totals 2,254 GPU-hours across 828 studies; the current shared
per-entry cap representation would require a 3,005.333-hour phase ceiling.
These are transparent scenario choices and arithmetic, **not measured full-study
costs, statistically guaranteed envelopes, necessary minima or spending requests**.
Batching, actual incumbent counts and an allocated-device measurement could
change the numbers substantially. No such full pilot is recommended or launched.

## Prepared next phase and blocker

The next action is part of this master: complete the final runtime measurements
on an allocated GPU, then refresh the full-study cost plan before pilot freeze.
The exact plan is `evidence/2026-10-01/scope-adoption/allocated-runtime-profile-plan.json`.
It uses the same six fixed development recipes, with six 360-second child caps:
**at most 2,160 child seconds (36 minutes) on one GPU**, plus coordinator overhead.
The prepared coordinator binds its source/plan, checks the GPU UUID and current
occupancy before every job, writes each attempt separately and refuses an
occupied device. It does not stop another process or manufacture an allocation.

The executed preflight in `allocated-runtime-readiness-01/preflight.json`
returned `blocked_device_occupied` and launched zero workloads. GPU3 UUID
`GPU-b8045e28-4433-ec7a-77a5-db0636748322` had another compute process holding
about 16.9 GB. Momentary zero utilization is not an exclusive allocation. The
readiness probe and inventory are evidence of the current external dependency;
they do not assert that every GPU is unavailable forever.

Resume when that GPU is available for the bounded window, or an equivalent
device is assigned and its identity is rebound before development execution.
Run the prepared coordinator with a new attempt name, preserve every result,
review resource adequacy and continue through STAT-03P without another routine
phase-boundary stop. A full scientific pilot still requires its separate exact
resource authorization after the measured plan is concrete. No user-supplied
success threshold, effect size, pilot ordering or scientific acceptance is needed.

## Whole-program disposition

Existing governance, packaging, searcher, scheduler and conformance repairs retain
their bounded engineering status. V01's 36 complete trajectories and nine exact
missing-cell refusals, and V02's 10,000 cases/eight scenarios/mandatory suite,
have fresh final-source PASS and V16 PASS receipts in the structured register.
Earlier source snapshots and the original V01 INCONCLUSIVE result remain history.

STAT-03P / PILOT-01 / CAP-01 / PPO-01 remain open. V03 full mutation acceptance
still follows final validator/protocol readiness under its retained six-hour
cap; historical mutation diagnostics are insufficient. REL-01 remains blocked,
including the shipping-default disposition. PRI-01 remains optional and opt-in;
its two retained development failures are not waived. All later-tier work stays
behind its recorded release/scope dependencies. The master is not complete.

Final verification receipts are added to the register after reconciliation.
The broad pre-reconciliation run retained 556 passes and one scope-receipt
binding failure; the new technical rebinding had not yet been registered. This
is repaired by registering the exact existing-scope receipt, not by weakening
the test or fabricating another user approval.

After exact receipt registration, the final integrated suite passed **557 tests** (`broad-tests-r6.xml`). Protocol consistency, all generated program views, Ruff and whitespace checks passed. The final readiness record verifies adopted scope, the nonfutile ideal reservation and preserved archives; it still reports the twelve missing budget/allocation inputs and no phase freeze. The continuation checker finds no eligible internal preparation and the documented allocated-device dependency; the master remains incomplete.
