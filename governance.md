# Program governance

The execution authority is [CONSOLIDATED_MASTER_AUTHORITY.md](CONSOLIDATED_MASTER_AUTHORITY.md). The pre-reconciliation proposal is preserved in [the program archive](archive/program-2026-09-28/governance.md).

## Controlled inputs and generated views

- `docs/program/program.json`: requirement dispositions, work items, dependencies, decision records, pinned specification inputs and immutable evidence bindings.
- `validation/protocols.json` and `validation/protocols/*.md`: protocol definitions. DRAFT/conflicting definitions stay unresolved; program reconciliation does not approve them.
- `CONSOLIDATED_MASTER_AUTHORITY.md`: maintained authority/scope prose plus a generated status block.
- `docs/progress.md` and `TRACEABILITY_MATRIX_v1.md`: fully generated views of the same register.
- `docs/REPAIR_PLAN_2026_09_26.md`: incorporated repair execution record, not a competing master.

## Workflow

1. Run `python tools/check_program_sync.py` and select an eligible work item.
2. Record the work item in progress. Keep one in progress per execution agent.
3. Implement the authorized work, run meaningful verification and retain evidence.
4. Update the work/evidence register and run `python tools/update_progress.py`.
5. Run the checker again. Before release, also run the full gate for recomputed acceptance.

At each transition, state whether the next action is an existing master-program item and give its ID. Continue authorized, eligible work rather than stopping at a task boundary. A stop requires a concrete blocker, resource limit or required decision; continue independent eligible work while resolving it. Proposed changes in direction require an explicit rationale and recorded program amendment. A finished amendment or work item does not mean the full program is complete.

A consistent BLOCKED program is valid. An unverified PASS, missing requirement, hidden protocol conflict, stale generated view or false completion is not. Source fingerprint changes make previous campaign receipts stale. Never update old metadata to manufacture freshness.

## Changes and decisions

Under **D-OBJECTIVE-EVIDENCE**, scientific results are determined by explicit derivations and frozen rules applied to reproducible raw evidence. Human review can find errors; it cannot approve a failed result or an unverified assumption into validity. The previous PI-certification and mandatory human holdout-selector requirements are superseded. Evidence validation and resource/release authorization are separate. No automated status label substitutes for proof or data either. See [the objective evidence amendment](docs/program/OBJECTIVE_EVIDENCE_2026_09_29.md).

Preserve scope exclusions and thresholds. Record substantive scope, identity, sample/design, budget and release changes with their rationale and explicit authorization before dependent confirmatory execution. Routine implementation fixes within existing authorization do not need repeated approval. Do not invent signatures, owners or staffing. The register uses execution roles where a named assignee is not established.

Specification inputs and protocol entries are hash-bound. A changed hash requires review and a corresponding register/decision update; regeneration alone must not silently accept a different rule. Historical sources are archived with their original bytes and hashes.

## Automation

`tools/check_program_sync.py` validates exact requirement/protocol coverage, local paths, dependency acyclicity, evidence hashes, receipt identity and generated views. It uses standard-library code and does not start Ray, mutation testing or PPO. `tools/update_progress.py --verify` checks byte-deterministic projections. CI executes these checks and negative governance tests.

`python -m tools.gate_check --phase tier0 --mode run` remains the scientific gate and recomputes V16 decisions. The static program checker does not replace it. No phase promotion can be inferred from old tags or the presence of the words “R1 Complete.”
