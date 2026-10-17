# Pilot readiness and resource boundary

This is STAT-03 / STAT-03P work inside the master program. The phase-specific
checker, `design_errors(candidate, phase="pilot")`, reports twelve missing
budget/allocation inputs on the default candidate. The previous review used
the generic checker, which also requires three planning alternatives, and
mistakenly described those alternatives as pilot prerequisites. That circular
requirement is withdrawn. The archived review and original JSON preparation
receipts remain historical evidence, not current readiness instructions.

A pilot requires a frozen experiment and a prospective sizing rule. Actual
effects and confirmation counts come from the independent pilot and are not
required before it. The accepted named exposed suite, equal task weights, nine
components, zero margins, Holm family alpha .05, .80 power, .95 simultaneous
planning confidence and maximum twenty confirmation vectors remain unchanged.
The forty-six-vector pilot can size only if every vector is jointly good.
Its .094468 sizing probability at hypothetical good-vector probability .95 is
a sensitivity calculation, not a measured effect or power claim.

The independent reconstruction in
`evidence/2026-10-01/phase-readiness/development-cost-reconstruction.json`
checks every fixed-profile artifact, rebuilds the nine-trial Ant GP trace and
its three selected policies, verifies the retained evaluation hashes/seeds,
and includes all six failed startup children in the measured resumption cost.

| Measured component | Seconds |
|---|---:|
| Six fixed GPU profile children | 1174.214 |
| Ant GP search child | 907.543 |
| Three successful retained evaluation children | 107.733 |
| Six failed retained startup children | 15.872 |
| Independent trace reconstruction, original run | 2.635 |

Successful search and evaluation children total 1015.276 seconds. Adding the
original trace reconstruction gives 1017.912 component workflow seconds.
Neither quantity is an uninterrupted wall time. Fifty trials is a safety
ceiling; the actual search budget was exhausted after nine trials. There is no
requirement to extrapolate that search into a fifty-trial study. Earlier
compiler/profile repairs, unmeasured preflight command overhead and elapsed
waiting are outside this explicitly scoped subtotal.

The successful retained evaluator set the requested CUDA environment, but
its runtime guard returned early because the sampling contract was omitted.
Its historical actual backend therefore was not independently recorded by
that guard. The original runner is archived and hash-bound. The repaired
worker supplies the contract, and behavioral tests reject changed plans and
wrong runtimes before evaluation. No historical measurement is retroactively
claimed to have passed the new check.

The conditional proposal makes the existing twenty-search-unit resource
scenario concrete: task search budgets are 2820/5160/3660 seconds for
Ant/HalfCheetah/Hopper; overshoots are 240/420/300 seconds; policy caps are
60/120/60 seconds. At the fifty-policy safety ceiling this is 1899.8 hours of
scenario work for 828 studies. The current shared per-entry campaign cap
requires an explicit total reservation of 2533.067 hours. These are engineering
ceilings, not necessary minima, efficient recommendations, uniform timing
bounds or evidence of adequate power. Owner and allocation remain unassigned.
A separate proposal can freeze those conditional scientific inputs without
claiming resource permission; the default candidate remains unfrozen.

The preparation sequence is: reconstruct measurements; bind the exact
conditional task/suite/resource proposal; verify the pilot-specific contract;
refresh current-source conformance; and exercise the actual readiness checker
through its final resource-authorization refusal. No pilot or confirmation
work is launched by those checks. Actual assignment requires a fresh exact
phase freeze and a hash-bound allocation receipt before any scientific child.
The independent pilot and its spending authorization are STAT-03P/PILOT-01
obligations; they are not prerequisites for completing the STAT-03 framework
or the VAL-01 validator repair. Mutation readiness proceeds independently.

Generated master status and the final readiness receipt identify which source
and campaigns are current. The master and Tier 0 remain incomplete.
