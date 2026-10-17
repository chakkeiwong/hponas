# First repair packet — SPEC-02A / SPEC-02

Status: **prepared recommendation for D-SCHEDULER; not an adopted default or scientific protocol**. This addresses the existing Tier 0 ASHA/median obligation. Its preparation is complete; implementation remains SPEC-02.

## What is already specified

The survey requires ASHA plus a median rule based on running averages and completed trials. Study currently submits separate endpoint evaluations and receives the result only when each finishes. Completion of an endpoint evaluation is not evidence that the full training trial completed. Current promotion also stops unsuccessful paused candidates permanently.

The independent promotion reference is the previously retained Syne Tune **0.13.0** wheel. The [probe](evidence/2026-09-29/spec-02a/probe_reference.py) executes its exact rung and promotion classes, removing only the import of classes already loaded from the same wheel. Both original source files and their license are retained. The [case record](evidence/2026-09-29/spec-02a/reference-cases.json) binds those bytes and the current project source. These are bounded policy probes, not a full vendor or scientific campaign.

## Reproduced behavior

All cases below minimize loss with eta=3 at fidelity 1, promoting to fidelity 3.

| Observations / event | Current result | Reference / required behavior |
|---|---|---|
| One score `[0]` | Promote the sole trial | Wait: fewer than two observations provide no cutoff. |
| Three scores `[0,1,2]` | Promote all three | Cutoff 2/3; only the best qualifies. |
| Four tied scores `[1,1,1,1]` | Promote two by quota | All four eventually qualify at the tied cutoff; one dispatch per scheduling request, no repeated promotion. |
| First scores `[0,1,2,3]`, then `[100,101,102]` | First promote trials 0/1, permanently stop trial 2; it never resumes | Initially leave trial 2 paused. After late arrivals change the cutoff, it becomes eligible and promotes. |
| Five live reports, no completed trial | Stop the fifth on the live-value median | Do not derive a completed-trial reference median from these reports. |

The probe found **four disagreements in seven static rung cases**, plus the later-arrival and median counterexamples. Matching a few other populations does not close the mismatch. Existing lifecycle tests intentionally encode the current quota/bootstrap policy and must be migrated with the behavior; they cannot serve as its independent oracle.

## Recommended contract

1. **Reference promotion.** Use the pinned Syne Tune promotion policy: require two observations, use the linear 1/eta quantile, preserve equality at the cutoff, and keep candidates paused while ineligible. Already promoted candidates remain in the reference population but cannot dispatch again. Prefer the highest promotable rung, as the reference scheduler does. Separate objective-direction normalization from ranking so maximization/minimization agree.
2. **Explicit compatibility.** Preserve the old bootstrap/quota behavior under an explicit compatibility policy and bind the policy identity in checkpoints. Reject implicit recovery under a different policy. Compatibility behavior must not be called reference-conformant ASHA in validation.
3. **Streaming and lifecycle.** Define a versioned event contract for progress reports, completion, failure, cancellation and pause/resume. Reports carry root trial identity, monotonically increasing resource step and metric. Study and both executors must deliver decisions while evaluation runs. Duplicate events are idempotent; stale progress cannot revive a stopped or completed trial. A completed rung evaluation is distinct from terminal completion of the full trial.
4. **Median reference.** On a declared report grid, compare the current trial's arithmetic running average through the current step with the median of completed reference trials' running averages through that same step. Do not mix running, pruned or failed trials into the completed reference population. Preserve a startup guard (proposal: five completed references) and specify it in configuration/checkpoints. Do not interpolate missing report steps silently. A disabled rule or an endpoint-only objective must not be presented as streamed median conformance.
5. **Continuation and accounting.** Promotions carry checkpoint/resume information and root identity. A workload which restarts rather than resumes must declare that behavior and charge all repeated work. `Study.budget` currently limits new configurations, not total compute; retain that meaning and introduce a separate measured compute cap for experiments. Do not claim incremental-fidelity savings from an endpoint rerun.
6. **Insufficient full-fidelity evidence.** Exhausting the declared budget with only low-fidelity or paused trials is an explicit incomplete outcome, with its ledger/checkpoint preserved. Do not manufacture a full-fidelity incumbent, promote all trials to avoid the condition, or silently substitute the best low-fidelity score. The public error/result representation is an engineering detail to specify and test in the repair.

The survey's “always-on” median wording and its performance/default consequences also need a visible release disposition. A functioning streamed implementation is required; deciding its shipping default must not be hidden inside a compatibility migration or a local unit test.

## Implementation slices and exit checks

| Slice | Files / behavior | Required evidence |
|---|---|---|
| SPEC-02 promotion | Scheduler state, cutoff/ties, paused versus stopped, highest-rung priority, policy identity and checkpoint migration | Pinned independent cases, late arrivals, repeated calls, both objective directions, restart equivalence; old policy explicitly tested under compatibility name. |
| SPEC-02 runtime | Study, executor interfaces, local/Ray reporting and continuation, measured accounting | A bad live trial stops before completing its expensive work; completed-reference data is available at the right event; cancellation/error/replay and resumed versus restarted charging are correct. |
| SPEC-02 median | Running histories, completed-reference set, startup guard and report-grid behavior | No completed references means no median cull; a current point better than the reference but a running mean worse than it is culled; missing steps and failed/pruned references follow the declared rule; recovery preserves the same decision. |

After each slice, run only the affected checks, preserve failures and update the master. After all slices, refresh affected installed checks and the V01/V02 validator design. Final campaigns belong to VAL-01/V03-03/REL-01 and retain their separate certification boundary.

The required ruling is whether this concrete reference/runtime contract should replace the old implementation behavior. It is one focused prerequisite for SPEC-02, not approval of all protocols or later-tier scope. The default/compatibility and startup details above are explicitly proposals, so they cannot silently become scientific assumptions.
