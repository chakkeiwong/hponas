# V03 phase repair and continuation

This is the existing V03-03 work in the master, not a new research direction.
The master already authorizes a six-hour, four-worker fresh mutation run after
implementation and validator repairs. Pilot resource allocation is separate.

Review reproduced three readiness defects. The fresh mutation workspace
omitted `docs/program` and its required test fixtures; mutmut's own nested copy
also omitted examples. Both copy layers now retain these inputs. The full
baseline then found a legacy PASHA test expecting a conflicting repeated
report to overwrite a score, contrary to the independently repaired contract.
It now tests idempotent reports, rejection of conflicting reports without state
change, and unchanged checkpoint/promotion behavior. An isolated-worker test
now distinguishes a true checkout from a mutation copy without `.git`; both
must refuse before producing any policy, and the original design-error
assertion remains required in the true checkout. Sanitized children do not
inherit fake Git provenance.

The first baseline has eleven failing/error cases: nine Ray startup cases
caused by unavailable sandbox sockets, the stale PASHA expectation, and the
copied-checkout expectation. All eleven are preserved in the first XML/log.
The eleven selected Ray/legacy-executor cases pass on the host with local
sockets. No Ray assertion was removed or weakened.

The original V03 markdown claims nonexistent module paths and disabled string
operators; the register claims a 200-mutant sample while the executed repair
profile requires the entire expanded population. Phase version 2.0 makes the
already stricter full population and default mutmut operators explicit. All
twenty implementation modules, covered and uncovered mutants, string mutants
and critical functions remain included. The 90% overall/per-module thresholds,
zero critical survivors, at least 100 mutants, at most 20% timeouts and at most
5% proved equivalents are unchanged. The next run uses zero exclusions.
This settles this concrete deterministic phase only; later scientific and
tier decisions remain open.

The runner freezes exact installed mutmut 3.8.0 source hashes, dependency
versions, Python, configuration, protocol, source/test identity, required
modules and critical functions before mutation execution. Independent decision
reconstruction checks those bindings and rebuilds statuses from the raw full
listing. A supplied aggregate or success label cannot replace the listing.
Unresolved abnormal outcomes or excessive timeouts are INCONCLUSIVE as the
original protocol requires; complete regular score/critical failures are FAIL.
Every attempt and workspace is retained.

Continuation is to finish focused verification, reconcile the program and
fresh finite conformance, run the full baseline in the actual execution
context, and execute the frozen population under the existing cap when those
checks pass. Failures are reviewed and repaired before a fresh attempt; no
selective rerun is promoted to acceptance. V03 completion requires the actual
full result, independent V16 audit and unchanged source, not this review.
