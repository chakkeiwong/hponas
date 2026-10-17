# Test-order and timeout reconciliation

This is execution-cost and coverage repair within the existing
`V03-03/ATTEMPT07-REPAIR` work item. Attempt 07 and its source remain unchanged.
The original six-hour/four-worker ceiling remains binding; no pilot starts.

## Corrected timeout interpretation

The earlier preparation review incorrectly described the prospective allowance
as 22+3t and its multiplier as unchanged. The retained pinned tool source shows
that it computes CPU seconds as `ceil(2 * multiplier * (t + constant))`, then
sets the forkserver wall limit to half that integer. Here t is the sum of
selected clean test-call durations. The active attempt leaves the settings
absent and uses the pinned defaults constant=1, multiplier=15. The staged
explicit settings constant=22, multiplier=3 produce approximately 66+3t wall
seconds, rounded up to a half second. Neither numerical setting was changed
during this correction. The earlier clean startup observations remain valid.

`timeout-policy-review-01/receipt.json` binds the actual runner, isolation and
configuration sources and evaluates their extracted AST expressions. For the
observed 147.374385-second streaming selection, the original wall limit is
2,226 seconds; the prospective limit would be 508.5 seconds at that same t.
This is not a prediction of future clean durations or an acceptance result.

## Preserve tests while making execution reproducible

The pinned forkserver forwards an unordered set of selected tests without the
duration sorting used by its direct-fork implementation. It can therefore
start live clusters before checking a simple wiring defect. The staged pytest
plugin sorts all selected items by fixed layer, module and node ID, and checks
that item identities and multiplicities are unchanged. There are no new test
exclusions, skips or mutation-specific branches. Stats, clean, forced-failure
and mutant invocations use this same order; the prescribed separate four-test
cancellation control retains its explicit order.

The permutation tests preserve exactly the same objects for every tested input
ordering. Freeze checks reject a missing, duplicate or substituted plugin. The
selected-order diagnostic ran all nineteen selected clean checks, including
live Ray checks, in 259.673 seconds; selection and order were independently
verified from its XML. A resource-policy mutant then failed in 7.031 seconds.
The full copied candidate baseline is a separate mandatory verification.

## Streaming and sampling coverage

New public streaming checks cover retry/resource policy, cumulative failure
cost, progress identity, exact attempt counts and partial reporting-channel
startup. Seven of eight observed streaming survivors are detected with a clean
control. The eighth changes a range upper bound but cannot reach an additional
attempt: success returns, the terminal Ray-error handler returns, other errors
propagate, and the polling loop never falls through. A narrowly bound twentieth
prospective rule checks that exact transformation. The updated proof bundle
verifies forty new transformations and rejects 157 negative cases.

The four mutations currently occupying the original runner also expose test
double weaknesses. Omitted `ray.wait` timeout was incorrectly modeled as zero,
although Ray's default is blocking; an exact virtual deadline could leave the
old double looping without advancing time. The staged double now enforces the
explicit nonblocking poll and positive remaining interval. A separate clean
control passes, and all four mutations fail in bounded fresh processes in
5.981–6.331 seconds. These are diagnostic failures, not rewritten outcomes of
the active campaign and not permission to exclude a mutation.

Additional sampling checks compare log-integer draws with an independent
inverse-CDF calculation, verify integer endpoints and singleton choices,
exercise initial scrambled/unscrambled Sobol sequences, preserve NumPy cached
RNG state, and test neutral conditional coordinates. They detect 21 observed
survivors. The final affected Ray/sampling group passes sixty tests; current
proof/order checks pass 299 tests plus three later freeze-refusal cases.

## Current candidate and continuation

`attempt07-integrated-preparation-04/manifest.json` retains 46 candidate files
and a patch at source digest
`36a5133021669151e2812ac83cadcad335e52ad0c1805f3512c23ddd2f921506`.
The running copied baseline binds this same source. Snapshot 22 reconciliation
has 598 prepared detections, 46 checked prospective proofs and 288 noncritical
residuals, with no unhandled observed critical survivor in that snapshot.
The inventory remains incomplete and none of these figures is a new kill score.

Continue the capped inventory, inspect later findings and retain its final
audited/raw evidence. Then adopt the verified candidate, refresh final-source
checks, and run the complete new mutation freeze before the already queued
conformance/readiness/governance refreshes. A capped incomplete result will be
retained as INCONCLUSIVE and fed into that repair sequence, never treated as a
completed acceptance gate. No change of scientific direction is proposed.
