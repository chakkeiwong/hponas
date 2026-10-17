# Runtime identity, atomic persistence and modern-GP preparation

This is further execution of `V03-03/ATTEMPT07-REPAIR` within the existing
master sequence. Attempt 07 continues under protocol 2.6 on its unchanged
source. Its known veto, raw outcomes and original four proof rules remain
unaltered. All implementation changes described here are isolated candidates.

## Runtime and evidence identity

The prospective freeze now records installed dependency versions and rereads
them during calibration and at full execution completion. A changed runtime
refuses launch or completion. Retained evidence includes both calibration and
final dependency manifests; current-evidence verification and master freshness
also compare them. Versions are read without a cache. This establishes local
environment identity, not external package authenticity or byte-level package
attestation. The 139 runtime/governance checks and twenty later calibration
drift checks passed. Non-Python test-input binding remains separately enforced.

## Demonstrated persistence defect

A valid 255-byte target filename could be created normally but `atomic_json`
failed with errno 36 because its temporary prefix repeated the full target
name. The retained failing regression is a production counterexample. The
isolated repair uses a bounded hidden sibling prefix and `.tmp` suffix.
Serialization, fsync ordering, replacement, failure cleanup and old-or-committed
complete snapshots remain checked. The 186 persistence, Study and replay checks
passed. Fresh mutations of the repaired function yielded 42 detections out of
45, with a clean control; three JSON-indentation changes remain in scope.
Those new-source mutant IDs are not attempt-07 identities and are never joined
to that campaign. Reconciliation now requires matching generated-source hashes
as well as exact candidate-test bytes.

## Modern GP and updated replay evidence

Modern-GP checks cover seed zero, numerical thread isolation, unavailable
accelerator RNG, invalid restored seeds, both space APIs, acquisition budget
and objective direction, and checkpoint defaults and NumPy cached-normal state.
The current candidate detects twenty of the completed module's 42 survivors.
Existing refusal tests detect all nine training-data refusal survivors, so no
duplicate diagnostic tests were needed. A separate combined check passes all
345 current GP, raw-outcome, proof and phase-contract assertions.
The 329 validator/proof/raw checks also pass against a separate copy of the
actual instrumented libraries, including the current runtime-binding changes.

Two exact prospective arguments cover the remaining critical kernel/axis
transformations. The first binds the installed BoTorch factory source and
proves that its sole truth test treats False and None identically. The second
binds the concrete encoder, space, types and GP source: stacking a nonempty
list of fixed-length scalar vectors gives a rank-two matrix, whose dimensions
at indices -1 and +1 agree. The nineteen-rule candidate accepts only the exact
reviewed substitutions. The proof diagnostic verifies 39 new transformations
and rejects 154 negative cases; changed library bytes at the same version have
an additional refusal test. No exclusion has been granted to attempt 07.

The final original replay-module inventory is 418 kills and 126 survivors.
Its current test candidate detects 120 survivors, with a clean generated-source
control. The remaining two critical transformations have exact prospective
proofs; four noncritical diagnostics remain in the denominator. The full clean
baseline reported in revision 1.36 predates these changes and is not advertised
as a final-source baseline.

## Retained preparation and continuation

`attempt07-integrated-preparation-03/manifest.json` retains forty candidate
files and their patch, including the runtime binding and persistence repair.
Its source digest is
`a285e68f9e6b7b9c7a0bf588990e46f44e7def422bacab58e722e1caaca33d05`.
The main source still matches attempt 07's original freeze.

Snapshot 21 recorded 6,362 of 8,533 mutants. Its 922 survivors reconcile to
570 detected by exactly staged tests, 44 individually checked prospective
proofs and 308 remaining noncritical survivors. No observed critical survivor
in this snapshot lacks preparation. These are incomplete diagnostic counts,
not a predicted acceptance score or a completed campaign.

Continue the original capped inventory and review later critical and module
findings. Retain its final raw metadata, statistics, debug log and audited
receipt before adoption. Archive and repoint the historical four-rule argument;
then adopt only the verified repairs, repeat final-source checks and the exact
copied baseline, and execute `V03-03/FINAL-RECHECK`. Advance through the existing
V01/V02/V14, conditional pilot-readiness and master reconciliation steps.
Pilot allocation, scientific results, release and later tiers remain open.
There is no phase-boundary stopping request or change in direction.
