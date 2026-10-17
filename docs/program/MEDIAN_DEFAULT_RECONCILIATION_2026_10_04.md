# ASHA/median default reconciliation

This is the concrete preparation for `REL-01/MEDIAN-DEFAULT-DISPOSITION`.
It implements the existing objective-evidence and phase-order requirements;
it does not infer a performance result from engineering conformance.

`ASHAConfig.median_stopping` currently defaults to false. Explicitly enabled
median pruning requires a declared report grid, completed reference trials and
the startup guard. Endpoint-only workloads cannot establish this contract.
The completed SPEC-02 runtime/reference checks establish their finite behavior.

The survey describes ASHA plus median as the intended always-on default, while
the registered V06 consequence says ASHA becomes a default only after PASS.
V06 is at the Tier-1 gate; the roadmap explicitly lists a separate Tier-0 gate
without V06. Requiring a V06 PASS to enter Tier 1 creates a circular program.
Enabling the default before V06 would bypass its scientific rule.

The consistent policy is therefore: Tier 0 delivers correct, explicitly usable
ASHA/median machinery; automatic default status remains conditional on the
registered V06 result. The current opt-in setting is evidence-pending status,
not a waiver or proof of safety. A V06 PASS, its workload/reporting envelope and
all applicable vetoes must precede the source/default change and refreshed
validation. FAIL blocks promotion and triggers diagnosis; INCONCLUSIVE retains
opt-in status under the registered terminal/replication rule. An enabled median
still requires its independently verified report-grid/runtime contract.

At the retained attempt boundary, adopt this exact phase distinction in the
governing survey, master and requirement reasons together. Keep the intended
default obligation on T1-MF and keep code conformance on SPEC-02. Preserve the
earlier wording and all numerical criteria. D-MEDIAN-DEFAULT stays open until
those source records agree; adoption does not certify V06 or enable a default.
