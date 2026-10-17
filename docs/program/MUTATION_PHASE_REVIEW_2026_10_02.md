# V03 whole-library repair and execution review

This continues V03-03 under the master, with the existing four CPU workers and
six-hour campaign cap. It corrects the incomplete 20/21-module claims in the
October 1 review, retained unchanged as historical evidence. No threshold,
covered/uncovered population, existing module or string operator is removed.

The whole-library audit accounts for all 32 Python files: 24 required modules,
five deferred modules with existing work-item owners, and three import facades
without function/class bodies. LegacyGP is an explicit V01 reference backend;
architecture.py implements the declared NAS scope; priors.py supports LegacyGP.
All three therefore join the existing required modules. Shared optional code
stays included within required modules. A mechanical filesystem inventory now
rejects jointly incomplete source/config lists, new unassigned modules, missing
implementations, facade function bodies and hidden mutation exclusions. This
closes the ownership obligation already stated in P2 of the September 28
protocol reconciliation; it is not a new scientific direction.

Attempt 03 generated 7,472 mutants on the former 21-module scope. It was stopped
when the additional omissions were found. Raw outcomes: 3,066 killed, 322
survived, 42 uncovered, seven timeout, ten abnormal and 4,025 unchecked. V16
recomputed INCONCLUSIVE. There are 179 recorded critical survivors. Exit zero
from an interrupted tool does not establish completion; the runner now checks
individual unresolved outcomes as well. Every earlier attempt remains intact.

The master checker previously rejected the V03 v2 schema and raw records lived
outside the repository. New runs retain the exact original freeze, tool/input
bytes and complete listing inside their audited directory. Existing attempt
03 bytes are copied with explicit hash-bound relocation, restricted to stale
non-PASS historical evidence. Nested input hashes are checked by the master.
The live tree and copied unmutated source are checked after execution too.

The 374 surviving, uncovered and abnormal mutant diffs from attempt 03 are
preserved as diagnostics. They already expose inadequate boundary assertions
in reporting, streaming worker lifecycle and recovery. Some case-only NaN
literal changes are semantically equivalent under Python; they are not killed
by inventing assertions. The next full execution still uses zero equivalent
exclusions. Any later exclusion requires its exact diff and a checkable proof,
and cannot remove an observable diagnostic change merely by reviewer label.

Execution sequence within this master:

1. Verify exhaustive ownership, evidence retention, schema and interruption
   repairs, and synchronize the program and concrete protocol bindings.
2. Repair demonstrated reporting/worker/recovery test gaps, with independent
   observable outcomes and retained negative evidence. Review surviving diffs.
3. Freeze the final source/config/tool and execute the complete expanded
   population. Mutmut performs its clean and forced-failure checks first.
   Preserve every result, deadline and abnormal worker; no source edit during
   this execution and no selected diagnostic is promoted to acceptance.
4. Reconstruct results and repair remaining real failures. If equivalent
   exclusions are needed, prove each against its exact frozen diff before a
   subsequent complete decision. Refresh affected finite V01/V02/V14 checks
   and the conditional pilot readiness receipt on the final source.
5. Refresh the master and continue eligible work. Pilot resource allocation
   remains a separate real blocker; the 2,533-hour conditional scenario is
   neither a recommendation nor an authorization and will not be launched.

The earlier fixture-copy, PASHA duplicate-report, sanitized-checkout and Ray
cleanup repairs remain. Finite conformance receipts and conditional readiness
are stale after these source changes; they do not become fresh by relabeling.
The master, Tier 0 scientific results and release are not complete.
