# Attempt12 closure and readiness repair

Attempt12 completed `V03-03/FINAL-RECHECK` on source
`41510c628eb21d38fddba44f2c5f00ac66676de97bf48aabea612556f758c940`.
The independent integer reconstruction and V16 both pass. All 8,575 mutants
have raw outcomes: 8,169 killed, 391 survived and 15 timed out, with zero
unchecked or abnormal exits. Exactly 54 survivors have individually verified,
prospectively frozen equivalence proofs. The adjusted score is
8,169 / 8,506 = 96.04%; every required module meets its score criterion and
there are no unproved critical survivors. The 15 timeout identities match
Attempt11. The run took 20,287.4 seconds, within the six-hour campaign limit.
Attempt11's original FAIL remains unchanged.

The registered continuation independently accepted current-source V01, V02
and V14, including V16 for each. The copied baseline and both supported
installations remain bound to this source. `REL-01/FINAL-SOURCE-VALIDATION`
is complete. These engineering results do not establish V04-T0/V05
performance or authorize release.

The corrected host observer retained 690 observations with a maximum interval
of 30.170007 seconds. All 21 memory warnings were investigated. Concurrent Ray
test clusters, including one legacy default-CPU initialization, account for the
peaks. The maximum summed RSS was 27.46 GiB, while available host memory never
fell below 181.98 GiB. Four retained reviews verify cleanup of every associated
PID; the final host check also confirms campaign and supervisor termination.
No operator signals or campaign input changes were needed. Observer records
are health evidence, not scientific acceptance.

The original continuation then failed at the exact pilot readiness guard.
Crash recovery had restored the JAX plugins and historical device fields but
omitted `nvidia-cuda-nvcc==13.0.88` and `nvidia-nvvm==13.0.88`, both already
pinned by the design. The other 88 pins matched. The guard correctly refused
before any workload. This was an internal environment repair within
`STAT-03P/POST-MUTATION-READINESS`.

Only the two missing packages were installed in the dedicated CUDA environment.
The fresh verifier checks all 90 design pins, the frozen interpreter/environment,
actual GPU identity and a small compiled arithmetic operation. It then calls
the unmodified readiness guard and verifies the exact missing-resource-
authorization refusal and pilot futility boundary. The base scientific
dependency inventory, source, original prepared inputs, failed receipt and
accepted campaigns are unchanged. The repaired readiness receipt records all
these checks. Future runtime recovery must verify every design pin, then the
backend/compiler check and full phase guard, before declaring readiness.

The actual Tier-0 gate report meets V01, V02, V03 and V14. It remains BLOCKED
on the unexecuted statistical sequence, incomplete final phase binding and
the dependent master prerequisites. The first gate invocation failed before
evaluation because direct script execution omitted the repository from the
module path. Its log is retained; invoking `python -m tools.gate_check`
produced the actual report. A blocked exit code alone was not accepted as a
gate result.

`GOV-01/POST-MUTATION-RECONCILIATION` retains these original results, repair
receipts and gate report and refreshes the remaining dependency graph. The
next registered stage is `STAT-03P/RESOURCE-ALLOCATION`: a justified concrete
owner/device/cap allocation must precede a fresh pilot freeze. Conditional
readiness has been verified, but current evidence does not justify an
affordable complete allocation. The historical 1,899.8-hour scenario remains
a conditional cost calculation, not a necessary minimum or authorized spend.
Neither the GPU smoke nor mathematics establishes optimizer effects or actual
workload timing. No pilot, confirmation or release was performed.

The combined whole-program audit must find no eligible internal work before
execution can wait at this external dependency. It covers 34 work items,
93 requirements through the register checks, 19 protocol owners and six phase
guards. Open later-tier decisions and unexecuted statistical campaigns remain
explicit. The master program is not complete; its accepted sequencing and
scientific criteria are unchanged.

Evidence:

- [Independent mutation closure](evidence/2026-10-05/attempt11-repair-01/attempt12-closure-review-01.json)
- [Final engineering reconciliation](evidence/2026-10-05/attempt11-repair-01/post-attempt12-continuation-01/engineering-review.json)
- [Monitoring closure](evidence/2026-10-05/attempt11-repair-01/monitoring-closure-01.json)
- [Original readiness failure](evidence/2026-10-05/attempt11-repair-01/post-attempt12-pilot-readiness-01/verification-process.json)
- [Verified runtime repair and readiness](evidence/2026-10-05/post-attempt12-readiness-repair-01/verification-01/receipt.json)
- [Current Tier-0 gate](../../gate_reports/tier0_gate_2026-10-05.md)
