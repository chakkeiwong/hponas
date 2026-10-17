# Continued execution and master refresh — GOV-01 / GOV-02

Review date: 2026-09-29, Asia/Shanghai. Verification began on September 28, so its artifacts remain in [resume-review](evidence/2026-09-28/resume-review). This refresh is part of the existing master program. The full program remains incomplete and Tier 0 remains blocked.

## Findings and repairs

The initial synchronization checks passed. Further review found three problems that a generated-view comparison could not detect:

1. **The release command omitted program prerequisites.** `check_tier0_gate` combined six campaign audits and could print “Phase may close” without reading the master register. A [synthetic fixture](evidence/2026-09-28/resume-review/release-guard-before.json), with the campaign auditor mocked to PASS, returned PASS despite the actual DRAFT register, open D-PROTOCOL/D-TIERS and unfinished V03/PPO work. This fixture demonstrates the independent missing guard; it is not real passing campaign evidence.
2. **Remaining scheduler implementation was hidden in a completed tranche.** The ASHA/median counterexamples were preserved, but their requirements pointed to completed SPEC-01 and the final REL-01 review. V03-03 could become eligible after D-PROTOCOL even though scheduler changes were still required. STAT-01 also directed execution toward already completed specification and packaging work.
3. **A retired narrative still began with an active editing instruction.** `docs/progress_narrative.json` had a supersession footer but its opening still claimed to generate progress. Its purpose now points to the current structured register; all historical entries and the pre-edit bytes are preserved.

GOV-02 now makes the command check program consistency and evidence bindings, recorded protocol certification status, required decisions, unresolved Tier 0 requirements and protocol identities, unfinished Tier 0 work and transitive release prerequisites, and current passing registered receipts. Each campaign still undergoes independent V16 decision recomputation. Alternate artifact roots cannot stand in for the registered release evidence. A missing audit dependency blocks that campaign rather than granting a result. A mechanical PASS explicitly still requires REL-01 review and release approval.

The guard does not require REL-01 itself to be complete before checking its prerequisites, and unrelated deferred decisions do not block Tier 0. Positive and negative fixtures cover both points. No protocol, numerical acceptance rule or scientific result was amended.

SPEC-02 now owns the existing ASHA/median obligation, with D-PROTOCOL/D-TIERS still open. Both V03-03 and REL-01 depend on it. SPEC-01's title now describes its verified GP-prior/PASHA/CMA-ES tranche. These are execution corrections, not new product scope or an adopted scheduler policy.

## Verification and environment limits

| Check | Result | Scope |
|---|---|---|
| Pre-repair broad regression, default sandbox | 1,267 passed, 23 failed, 2 skipped | [Captured output](evidence/2026-09-28/resume-review/sandbox-suite-output.txt) preserves the final summary; the tool truncated some repeated tracebacks. All 23 failures were Ray startup timeouts. The retained GCS error identifies sandbox denial of sockets. |
| Three affected Ray files, permitted host execution | 34 passed | [JUnit](evidence/2026-09-28/resume-review/ray-host.xml), five-minute ceiling; no implementation edits to Ray. These overlap the broad selection and are not added to its pass count. |
| CMA-ES optional dependency restored to test search path | 16 passed | [JUnit](evidence/2026-09-28/resume-review/cmaes.xml). The initial base interpreter lacked `cmaes`; the existing `/tmp/hponas-spec-deps` target supplies it. The other broad skip is the tracked DRAFT class-naming policy. |
| Final affected governance/repair/audit selection | 100 passed | [JUnit](evidence/2026-09-28/resume-review/release-tests.xml). Includes the new release guard and existing evidence-integrity, audit-context, repair and claim-boundary checks. |
| Governance without scientific dependencies | 47 passed | [JUnit](evidence/2026-09-28/resume-review/governance-final.xml). Preserves the governance CI installation contract; these tests overlap the affected selection. |
| Installed governance update | PASS | [Receipt](evidence/2026-09-28/resume-review/installed-governance.json). Offline wheel build, 89 Python files matching source, new isolated installation target and blocked gate outside the checkout. Existing clean-resolved dependencies reused; no new platform certification claimed. |
| Lint, protocol structure and generated views | PASS | Recorded in [verification](evidence/2026-09-28/resume-review/verification.json); protocol structure is not PI certification. |

The shell default is the unrelated Python 3.11 `tf-gpu` environment, which lacks Torch and falls below the project's Python >=3.12 requirement. Scientific checks used `/home/ubuntu/miniforge3/bin/python` (Python 3.13.13); exact dependency versions are recorded in the receipt. The earlier verified Python 3.12/3.13 CPU environments remain intact. No dependency installation or environment deletion was needed to resolve the shell mismatch.

The full broad suite was not repeated after changes limited to governance tools and tests; the affected selection covers those edits. Optional prior performance was not rerun: its unchanged, separately recorded two failures remain open under PRI-01. Historical receipts remain stale after the source changes. The fresh gate also rejects historical V02's divergent GP trace; no campaign was rerun or relabeled.

## Continuation boundary

GOV-02 and this refresh are complete. The register now carries 24 work items: ten complete, seven blocked, seven deferred. There is no active eligible implementation item after the verified repair.

The pending design-direction question belongs to **D-PROTOCOL/D-TIERS**, under existing **STAT-01/STAT-02/SPEC-02** work: adopt the reviewed register's claim/gate mapping or retain the conflict for further ruling. Choosing that mapping alone will not certify the final experiments or resolve every numerical/reference question. The concrete proposals are in [protocol reconciliation](PROTOCOL_RECONCILIATION_2026_09_28.md), [scheduler conformance](SCHEDULER_CONFORMANCE_OPEN_2026_09_28.md) and [prior review](PRIOR_REVIEW_2026_09_28.md).

`validation/protocols.json`, `policy.open_decisions[D5].procedure`, requires: “PI certifies the final protocol set before any campaign spend.” The next dependent actions remain part of the master; their stop is due to these unresolved decisions and certification, not completion of the program. No additional campaign allocation, source reset, commit, tag or publication is inferred.
