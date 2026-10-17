# Independent holdout review package

This is **STAT-03/D–F within the existing master program**, updated by D-OBJECTIVE-EVIDENCE. The approved finite-suite claim requires verifiable sampling/exposure evidence. Reviewer identity is not a scientific criterion. The implementation agent has prepared factual inputs and a deterministic selection replay; no acceptance tasks have been selected and no environment has been executed.

The [machine-readable package](evidence/2026-09-29/stat-03/holdout-review-package.json) binds the installed Brax registry, all 12 environment sources, 11 direct XML assets, the shared base source, and a 487-file local code/example/test/validation scan. It records Brax 0.14.2 and the installed source commit. Copies are under `evidence/2026-09-29/stat-03/holdout-review-sources/`. The original review proposal and its source frame remain unchanged.

| Environments | Known facts | Current disposition |
|---|---|---|
| Ant, HalfCheetah, Hopper, Humanoid, inverted pendulum | Development, default or reference exposure was already recorded. | Excluded from the proposed fresh holdout frame. |
| Fast | Diagnostic environment. | Excluded. |
| HumanoidStandup, inverted double pendulum, Pusher, Reacher, Swimmer, Walker2d | Sources/assets are pinned; generalized is their declared default backend. No exact environment-name match was found in the scoped local scan. External and capability-specific exposure remains unknown. | Supporting exposure/lineage evidence required; none is established eligible. |

Source inspection is narrower than execution support. Swimmer explicitly rejects backends other than generalized; several other environments have spring/positional branches. No environment was instantiated, and no PPO throughput or resource requirement was measured. Related environments need lineage review, especially HumanoidStandup/Humanoid and double/single pendulum. A missing literal match cannot establish non-exposure outside this checkout or under another name.

Eligibility must follow from capability-specific development/exposure records and source lineage under a declared coverage scope. Unknown exposure stays unresolved. A signature cannot prove that a history is complete. Task count and coverage strata must be fixed before the private selection seed is revealed. The procedure ranks eligible IDs by `SHA256(private_32_byte_seed || NUL || UTF8(task_id))`, with lexical collision ties, and selects the committed counts within committed strata. Commit the algorithm/frame/counts and seed hash before implementation freeze; reveal and verify with the final task manifest. The new replay checks exact ledger binding, seed consistency and both entries' selections. It cannot verify real chronology or seed concealment from self-declared timestamps. Independently anchored records and their verifier remain required.

The previous request for a reviewer appointment is withdrawn. No organizational role assignment is required to decide a scientific result. Exposure provenance, selection chronology, task-count justification, power and resources remain agent-owned evidence obligations. The machine-readable source package is an immutable historical snapshot and retains its old empty reviewer fields; those fields are no longer scientific prerequisites. Nothing here establishes blinding, allocation or acceptance.

Reproduce the source scan using `prepare_holdout_review.py` in the evidence directory. It refuses to replace an existing package; a later scan or reviewed disposition must be saved as a new revision. Keep previous facts and hashes for the exposure audit.
