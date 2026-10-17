# Mutation isolation and attribution repair

This continues V03-03 inside the master. Attempt 04 on 24 required modules
retained 8,507 mutants. After 7,267.316 seconds, its direct-fork coordinator
exited SIGSEGV. Recorded outcomes were 6,067 killed, 230 survived, 31 timeout,
32 abnormal, 42 uncovered and 2,105 unchecked. V16 correctly reconstructed
INCONCLUSIVE; those counts do not establish trustworthy detection coverage.
Nine orphaned workers/services remained in the owned process group. All were
stopped with an exact-group cleanup receipt; no other job was targeted.

A stronger attribution check found a false kill: replacing the unused local
X_train assignment in LegacyGP _build_acqf with None was recorded killed, while
all eleven identical selected tests passed in a fresh process. The clean
control also passed all eleven; replacing torch.stack(self._X) with
 torch.stack(None) failed in the expected objective path. All three logs and
exact mutant identities are retained. The blanket LegacyGP kill count from
attempt 04 must not be used as evidence that every mutant was detected.

The pinned mutmut 3.8.0 already provides forkserver isolation for fork-unsafe
runtime libraries. Version 2.3 selects that supported mode, no warmup of test
modules and no automatic server restart. This avoids inheriting a pytest
session polluted by clean/statistics/forced-failure executions. It is a
plausible causal repair, pending actual calibration; no claim that the signal
11 root cause is conclusively established. Exact installed tool bytes remain
unchanged. Tool logging and owned-process-group cleanup are now explicit.

Survivor-led tests now cover real NAS activation/normalization/tensor shapes,
checkpoint compatibility, invalid architecture inputs, streaming child
messages, public result serialization and checkpoint durability. One further
TPE defect was reproduced: modifying a returned proposal or submitted nested
metadata could rewrite its accepted ledger. Deep input/output ownership now
prevents this; checkpoint replay semantics are preserved. The latest focused
repair receipt has 187 passing checks and preserves the earlier failing test.

V02's fresh run failed its crash-retry case while 303 other assertions passed.
Standalone reproduction, the six-test Ray module and then the exact 304-test
runtime context all passed with diagnostics. This does not explain away the
failure; its audited FAIL remains current until source changes make it stale.
Failure-state capture will be kept available for the next full execution. The
failure is not called a timing failure without the actual failed result.

Required sequence: reconcile this review and protocol; run the same actual
mutmut runner on clean/unused-assignment/broken-stack controls in a fresh
workspace within a 900-second diagnostic envelope; independently reconstruct
its statuses. Only if calibration succeeds freeze and execute the full
population under the existing six-hour/four-worker cap. Preserve every failure
and do not infer PASS from partial or selected results. After source repairs,
refresh V01/V02/V14 and the conditional pilot proposal; actual pilot allocation
remains the separate external blocker. No scientific or release gate is done.
