# Recovered runtime and Study test order

This continues `V03-03/ATTEMPT08-REPAIR` and
`PKG-01/ATTEMPT09-INSTALLATION` within the existing master program. Revision
1.47 and the original test bytes are archived before this refresh. Attempt 08
remains INCONCLUSIVE; its outcomes and frozen rules are unchanged.

The recovered exact copied baseline passed 2,838 tests with one existing skip
and thirteen slow deselections in 366.945 seconds. Its source is `64228065…`;
it establishes recovery on that source only. All start/end source, fixture and
dependency identities match. Both failed pre-crash baselines remain evidence.

Runtime review found that the fourteen new, short Study checks were placed in
the integration directory and therefore ran after costly Ray tests under the
existing deterministic ordering. The two files are moved, without changing any
bytes, to `tests/unit/test_study_progress_controls.py` and
`tests/unit/test_study_batch_controls.py`. No selected test is removed and the
ordering plugin is unchanged. Current source is
`888d1f3bd7f62f4dd2c87087facf6a07ac0d6b487ca414f0271d6018f40ceadd`.
A new exact copied baseline is required and uses `baseline-plan-02.json` in
the crash-recovery evidence directory.

The prior generated-clean progress diagnostic detected all seventy selected
progress/promotion survivors, including all twenty-five observed critical
survivors. These survivors consumed 12,378.871 worker seconds in attempt 08.
The batch diagnostic detected twenty-three of thirty-four selected survivors,
with seven remaining and four diagnostic timeouts. Its receipt was written, but
the process did not finish before its 360-second outer timeout. Preserve that
incomplete process outcome; neither timeout nor unchecked outcome is a kill.
The new ordering targets demonstrated avoidable runtime. It is not a measured
whole-campaign wall-time bound or proof that the six-hour campaign will finish.

The 1,026 previously unchecked mutations still require the full inventory. They
are concentrated in Study construction, acceptance, running, snapshots and new
trials, encoding and knob validation. Existing public lifecycle, recovery,
encoding and input-validation tests exercise those paths, but their presence
does not establish detection of unexecuted mutations. The next complete run
retains every outcome and applies the same protocol 2.7 criteria. Any remaining
critical, incomplete or abnormal outcome returns to the registered repair loop.

Both isolated installation environments have been reconstructed in persistent
storage. All seventy-two Python 3.12 and 107 Python 3.13 dependency versions
match the retained manifests, and both dependency checks pass. Reconstruction
took 322.571 seconds, with 3,768,366,390 bytes of retained cache/interpreter/wheel
data, within the existing limits. The recovered Python 3.12 patch is 3.12.11,
previously 3.12.14; this is a fresh supported-interpreter check, not identical
interpreter restoration. The scientific interpreter and its restored 253
dependency versions remain unchanged. The sandbox network failure is preserved.

After the current-source baseline and preparation review pass, verify the new
wheel and all installed checks/examples within the existing two-CPU,
900-second verification limit. Then run the registered `V03-03/FINAL-RECHECK`
with mandatory same-workspace calibration, four workers and the unchanged
six-hour cap. Only complete independently reconstructed V03/V16 acceptance
enables the existing conformance, conditional pilot-readiness and governance
continuation. No pilot allocation, confirmation spend or release is authorized.
