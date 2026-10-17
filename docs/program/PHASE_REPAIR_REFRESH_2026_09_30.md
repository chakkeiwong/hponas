> Revision 1.20: [scope adoption and current review](SCOPE_ADOPTION_REVIEW_2026_10_01.md) supersedes pending-scope, pre-pilot-effect and unmeasured-installation status below. Follow the structured continuation queue and current master; historical outcomes are retained.

> Revision 1.19: the [phase sequence repair](PHASE_SEQUENCE_REPAIR_2026_09_30.md) supersedes earlier all-external-blocker and pre-pilot-effect requirements. STAT-03 execution is active; historical checkpoints below remain preserved.

# Continuous execution: repair, refresh, advance

This is the operating rule for the existing master program, authorized by the
user on 2026-09-30: continue until a concrete blocker, repair what can be repaired
between phases, refresh the next phase and keep going. It grants no new scientific
claim, release permission or unbounded experiment budget.

At each work-item or phase boundary, the implementation agent must:

1. Review the completed deliverable and raw evidence against its actual scope.
   Record failures, newly exposed defects and stale evidence. Keep the earlier
   artifacts; a newer success never deletes a counterexample.
2. Repair eligible defects inside the current authorization. Run the affected
   checks. A broken check, an unimplemented verifier or a draft plan is work to
   perform, not an external blocker.
3. Refresh the structured continuation queue: dependencies, evidence, unknowns,
   resources and concrete completion criteria. Record any change of direction
   before dependent execution. Preserve adopted outcomes and error/power rules.
4. Regenerate the master views and run protocol/program consistency checks.
   Identify which prior receipts became stale and what must be revalidated
   before the dependent phase. Avoid rerunning unrelated campaigns after every
   intermediate edit; bind the final source at the appropriate freeze.
5. Select and execute the next eligible task immediately. An engineering repair
   can finish while scientific acceptance remains blocked. Move to another
   eligible preparation task if its sibling needs unavailable facts or resources.

`python tools/program_continuation.py` evaluates the structured queue and reports
CONTINUE while any eligible repair/preparation remains. The code checks missing
dependencies, cycles, unsupported completion, and purported external blockers
without evidence and an explicit resumption condition. It is a planning check;
it does not certify scientific truth or launch a campaign.

A stopping report is justified only by full completion, an explicit user pause,
or a concrete dependency that prevents the remaining authorized work from
proceeding. Missing external data, unavailable infrastructure, a measured resource
limit, or required spending/release authority must be identified precisely with
the attempted resolution and the condition that would unblock it. Stop only the
dependent branch while other eligible tasks exist. A progress report, elapsed
conversation length, passing tests or a phase boundary is not a stopping reason.

The queue distinguishes agent-owned implementation from external facts:

| Existing work | Authorized work to complete now | What it cannot manufacture |
|---|---|---|
| GOV-01 | Enforce this handoff and expose the next eligible step | Scientific PASS or release authority |
| STAT-03/D–F | Exposure/chronology evidence contracts and verifiers | Undocumented external history or a past public commitment |
| STAT-03/F / VAL-01 | Fresh-process execution/isolation evidence and negative checks | Independence from labels or seed numbers alone |
| STAT-03/E | Prospective rank sizing/stopping mathematics and verifier | A transferable expected PPO effect without observations |
| STAT-03/F / VAL-01 | Exact reference/scope review for V01/V02 | All-seed equivalence from finite matching traces |
| STAT-03/F / CAP-01 | Costed executable resource plan | Measured runtime before measurement, or permission inferred from hardware |

The active scientific work remains STAT-03/F. These steps belong to this master;
they do not constitute a new program. Before stopping, the queue must expose
which of these have actually been completed and which require specific missing
inputs. Unfinished software cannot be relabeled an unavailable scientific fact.
