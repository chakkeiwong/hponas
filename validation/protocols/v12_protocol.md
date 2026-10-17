# V12 — finite ranked warm-start conformance

Version 2, prospectively adopted under D-WARM-FINITE on 2026-10-08. The historical
empirical warm-start registry, contradictory mixed-space TuRBO markdown and
source-scanning validator are preserved in
`archive/program-2026-10-08/before-warm-finite-migration/manifest.json`.
They cannot be used to accept this new finite contract or vice versa.

`validation.warm_finite_contract.contract()` and the identical registry entry
fix six exposed cases: matching and shifted curvature, absent compatible
history, ties, maximization and different historical measurement scales.
Each executes six historical Studies of four trials and warm/cold target Studies
of six trials. Every evaluation performs four scalar gradient updates.
Exactly 144 updates per case, 864 total, are retained incrementally and in raw
per-study records. Warm histories are synthetic numerical training studies,
explicitly distinct from the old precondition of ten immutable real histories.

The model is w[0]=1, w[k+1]=w[k]-eta*h*w[k]. Independent powers reconstruct every
state and the signed, scaled endpoint. The target loss is w[4]^2, with optimum
at eta=clip(1/h, 0.125, 0.875). Independent pairwise counts reconstruct exact
within-study midranks, stable identity tie breaks and deduplication. Held-out
task, transformed-space and after-cutoff histories are excluded. Only three
candidate configurations transfer; all target observations require new work.
The base random stream is independently reconstructed. No ranking of warm
versus cold outcomes is an acceptance criterion.

After two target commits, interrupt before the next physical update, retain the
pending Store checkpoint and restore it with the frozen selection. The recovered
pending proposal, completed prefix, remaining stream and all physical work must
agree. Bind the closed SQLite backup and compare its original histories and
study snapshots against the raw evidence. Reconstruction never calls training.

PASS requires all fixed cases and their exact logical controls to conform.
Floating training comparisons use 2e-12 absolute and 2e-10 relative tolerances;
these are declared numerical engineering envelopes, not a human success
threshold or a rigorous universal floating-point bound. Complete contradiction
is FAIL. Interrupted/incomplete generation is INCONCLUSIVE and retains all
attempted work. Identity/source/protocol/runtime defects withhold acceptance.
An audited failure is still a failure.

Before official execution, freeze exact qualified source, runtime, protocols,
supervisor and output path. Allocate one generation across six fixed cases and
three independent reconstructions in two 300-second CPU-only processes. Use
one CPU affinity and one numerical thread. Exclusive start files consume the
allocation even if interrupted; no replacement slots or favorable reruns.

## Known Issues

PASS certifies finite opt-in ranked seeding only. The old empirical speedup,
default activation and real-history eligibility claims remain unestablished.
No mixed-space TuRBO, surrogate transfer, deployed service or integrated release
follows. The registry retains the historical `dist_beta_gate` identifier for
traceability; this finite V12 is an independent local contract. APP-11 remains
an open service obligation with a separate operational protocol.
