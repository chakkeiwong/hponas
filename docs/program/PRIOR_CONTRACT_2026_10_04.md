# Retained prior-method contract

This executes `PRI-01/REFERENCE-RECONCILIATION`. It retains the paper-linked
NePS revision `3f7475b5afaaacdace56f25357ddfbf0e5616157` and experiment revision
`fe8632a5ee775ea76fd0fe2d76776d83cef35427`. The manifest, source and licenses in
`evidence/2026-09-28/pri-01/reference` are immutable. The newer NePS revision
is a comparison, not an interchangeable oracle.

The registered PriorBand method means the paper's Hyperband portfolio with
synchronous promotion and its geometric/dynamic sampling policy. The currently
shipped `PriorBandSampler` remains an explicitly uncertified compatibility
heuristic. Relabelling its ASHA-like rung counter cannot satisfy V11.

The implementation must expose a reproducible distribution with sampling,
log-density, support, mode/default and a versioned coordinate recipe. Sampling
and density use the same base measure, including transformed-coordinate
Jacobians. A strictly positive mixture over the declared domain preserves
support under wrong advice. Finite weighted candidate resampling is not exact
sampling from an arbitrary density. piBO may retain density-only callables
without asserting that they provide a PriorBand distribution.

Before incumbent activation the normalized weights are
`random=1/(1+eta**r)`, `prior=eta**r/(1+eta**r)`, `incumbent=0`.
Activation requires both the original first-bracket resource threshold and an
observed highest-rung result. The retained source counts completed rows using
`sum(rung_map[r])`; its observed-config table contract must be reproduced,
with duplicates/pending/failed events independently checked. Incremental
executor costs and this reference policy's bookkeeping are separate records.

The original default `find_incumbent()` selects the lowest loss across the
observed rows. It does **not** restrict that selection to full fidelity. The
previous review overstated that property. The optional explicit-rung call
contains a nonterminating loop and is not exercised by the reviewed default
path; it must never be silently copied into a public entry point.

Dynamic scoring uses the highest rung with at least eta observations and
`max(n//eta, eta)` top configurations, rank-weighted prior/incumbent densities,
and normalized score sums. Sparse rungs fall back to lower rungs, then eta:1
prior/incumbent proportions. Local mutation uses per-coordinate probability
.5 and normalized standard deviation .25, with the original bounded retry
semantics. Default-first evaluation at target fidelity remains part of the
method. Full mutation/sampling details must be checked against the pinned
parameter classes before integration; clipped raw Gaussian noise is insufficient.

The executable finite fixtures in
`evidence/2026-10-04/execution-review-03/prior_reference_fixtures.py` check the
original weighting, activation boundaries, missing-result handling, sparse-rung
fallback, top-set scoring and incumbent-fidelity distinction. They do not claim
full-package equivalence. Implementation conformance additionally needs ties,
positive finite densities, deterministic sampling, exact bracket/continuation
traces, duplicate-event rejection, all resource boundaries and checkpoint replay.

piBO retains `log(qEI) + beta/n * log(prior)` for the current log acquisition,
with observation count and positive support checked independently. For batches,
the averaging extension must have its own declared scope; a single-point paper
formula cannot silently certify arbitrary batch behavior.

V11a and V11b require each named method to meet its own frozen criterion.
Pooling methods cannot hide a failing method. Retain the original development
failures and exposed-task/saturation history; choosing easier-to-win tasks or
favorable seeds after viewing outcomes is not a repair. Final tasks, exact
method/reference envelopes, sizing and separate resource allocation remain
later phase work. D-OBJECTIVE-EVIDENCE supersedes the historical request for
PI scientific signoff; raw evidence and frozen rules determine results.
