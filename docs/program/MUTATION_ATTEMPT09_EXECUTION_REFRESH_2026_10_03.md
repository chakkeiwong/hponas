# Attempt 09 execution refresh

This document records the next repair and refresh step in the existing
`V03-03/ATTEMPT08-REPAIR` work item. It does not create a new scientific claim,
change the V03 protocol, alter the mutation threshold, or authorize a pilot.

The repair is source-bound to digest
`6422806522fe0a2d3f906e1083810023182600ebf691f2a446b016678024ffe7`. Two
maintained integration modules now exercise Study progress, promotion identity,
cancellation cleanup, batch cost and elapsed-time accounting, and interruption
cleanup. The focused JUnit receipt records 14 passing tests. The independent
candidate diagnostic separately checked all 70 selected Study progress and
promotion survivors, including the duplicate-promotion transformation, while
the unchanged generated source passed.

A complete non-slow baseline is required before freezing the next campaign. An
initial run in the base interpreter was retained as an environment diagnostic:
the interpreter did not expose the declared optional `cmaes` distribution and
therefore produced dependency-driven failures. The baseline is being repeated
with the pinned `/tmp/hponas-spec-deps` overlay that is already used by the V03
runner; this changes no source or test input. The repeated result is the only
baseline eligible for the campaign prerequisite.

After the baseline, the retained Python 3.12 and 3.13 environments will be
refreshed offline from the same digest with no dependency resolution. A fresh
V03 campaign may start only after the installation and baseline receipts are
complete and the master identities reconcile. The campaign remains objective:
raw outcomes, independent integer reconstruction, V16 audit, and every frozen
protocol criterion determine PASS/INCONCLUSIVE. Human review records evidence
but does not determine scientific acceptance.
