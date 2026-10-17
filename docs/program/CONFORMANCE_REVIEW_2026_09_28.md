# Conformance review — TST-01

TST-01 is an existing master-program prerequisite for V03-03. It resolves stale
conformance placeholders; it does not certify algorithms, a release, or operating
conditions that were not exercised.

| Previous placeholder | Executed check / current disposition |
|---|---|
| Store atomic writes and partial writes | A failed snapshot transaction restores the ledger and query projections. A separate connection sees the previous complete snapshot while a writer has an uncommitted transaction. |
| Store kill -9 recovery | Kill a spawned writer after its ledger update but before committing its trial projection. Reopen the database and compare the snapshot, study, trial rows and artifacts with the prior commit; run SQLite integrity checking. |
| Concurrent writes | Four local connections open together and write twenty distinct records; all survive. A second committed update to the same trial becomes visible on the first connection without duplicate rows. |
| Corruption detection | Invalid SQLite bytes raise DatabaseError without resetting the file. Invalid JSON payloads raise JSONDecodeError without replacing the stored bytes. This is detection of these specific corruptions. |
| Backup recovery | **Unsupported Store API**, tracked in OPS-01. No backup/restore implementation or certification is implied by SQLite primitives. The empty skipped test is replaced by this explicit disposition. |
| ASHA configuration validation | Removed three stale skips; invalid eta, nonpositive minimum fidelity and reversed bounds now execute against the existing validation. |
| ASHA protocol | Removed the stale “not implemented” skip. The test now reports, promotes, restores state and completes a real scheduler lifecycle. |
| Executor timeout | Removed skip; a process deadline returns timeout and terminates a sleeping objective. |
| Objective OOM | Removed skip; an objective raising Python MemoryError produces a failed result with diagnostics. **Host OOM termination and multi-node recovery remain OPS-01**, not a promise made by this test. |
| Empty search space | **Unsupported optimization contract**, retained as an explicit skip and assigned to SPEC-01's baseline-contract disposition. Mutable empty space declarations used while adding knobs are distinct from running zero-dimensional optimization. |
| Custom Kernel/GaussianProcess/ExpectedImprovement wrappers | Three files target nonexistent `hponas.models.gp` / `hponas.acquisitions` APIs. They remain explicitly skipped; implementing these wrappers is not silently added to the program. Actual GP behavior is exercised through `tests/unit/test_gp_searcher.py`, `tests/conformance/test_searcher_contract.py`, `tests/integration/test_gp_searcher_integration.py` and `tests/integration/test_study_gp.py`. The required GP prior and acquisition semantics remain SPEC-01/V01/V03 obligations. |
| Every class named Test<Class>Validation in one file | INPUT_VALIDATION_POLICY.md is explicitly **DRAFT, not adopted**. Keep its structural proposal skipped; replace its false “1/21 classes / blocking mutation” explanation with this disposition. Behavioral validation now exists across the checkpoint, executor, scheduler, Store and searcher tests. This does not assert exhaustive input validation. |

The Store visibility test first failed: `load_study_snapshot()` issued `CREATE
TABLE IF NOT EXISTS`, which sought a write lock and delayed the reader until the
writer committed. Schema creation now occurs during Store initialization. Snapshot
and Pareto reads execute queries without schema writes. Existing databases obtain
the tables when opened; the snapshot update remains one transaction.

The envelope is local SQLite WAL on this Linux host, with independent connections
and bounded test processes. It is not shared-filesystem, power-loss, multi-node,
backup or arbitrary corruption-repair certification. Remaining capability work
stays in SPEC-01 and OPS-01 rather than disappearing from the master.

Verification: the Store repair selection passed 42 tests, including all six real
recovery checks. The scheduler/executor/protocol selection passed 81 tests. Exact
logs, JUnit output, source/test hashes and the pre-repair failure are preserved in
`docs/program/evidence/2026-09-28/tst-01/`. The full suite is recorded separately
after the current implementation work is frozen.
