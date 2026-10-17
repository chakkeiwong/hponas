# Attempt 09 repair plan

This is the next execution of existing `V03-03/ATTEMPT08-REPAIR` and
`V03-03/FINAL-RECHECK` in the master program. It follows the capped attempt 08
closure and the source-bound repair review; it changes no mutation threshold,
protocol rule, equivalence allowance or resource cap.

The adopted repair adds direct maintained contracts for Study streaming progress,
promotion identity and cancellation cleanup, batch elapsed/cost accounting,
legacy scheduler dispatch and interruption cleanup. The contracts pass unchanged
code and detect all 70 selected generated `_on_progress`/`_promotions` survivors,
including the duplicate-promotion `continue` to `break` transformation. The
candidate diagnostic is retained separately from campaign evidence; the maintained
copies are now in `tests/integration/` and part of the frozen source.

The current source digest is
`6422806522fe0a2d3f906e1083810023182600ebf691f2a446b016678024ffe7`. A complete
non-slow baseline must pass before the campaign freeze. The fresh V03 campaign
uses the exact scientific interpreter `/home/ubuntu/miniforge3/bin/python`,
mandatory same-workspace calibration, four mutation workers and the existing
21,600-second total cap. Every start, source identity, calibration output, raw
listing, metadata file, timeout and final audit is retained. Expiry or any
abnormal/unproved critical outcome remains INCONCLUSIVE and returns to this repair
loop. A passing audit alone cannot establish mutation acceptance.

After a complete independently reconstructed V03/V16 PASS, execute the existing
final-source V01/V02/V14 conformance plan, refresh the installed wheel if the
source changes again, rebind conditional pilot readiness, and reconcile the full
program. No pilot allocation or release authority is created by this plan.
