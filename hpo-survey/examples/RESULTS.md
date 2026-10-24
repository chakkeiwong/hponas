# DOC-01 application evidence, 24 October 2026

The source checkout and manual include these companions; the wheel does not.
Install hponas with its TPE extra before using them in a separate environment.
The reviewed workspace commands and limits are in docs/PROGRAM_OPERATIONS.md.

- Design: design.json (frozen before execution).
- Fit/Study integration: application_examples.py.
- Independent scalar/NumPy reconstruction: independent_checks.py.
- Six focused numerical/negative-control tests: test_application_examples.py.
- Executable guide snippet: manual_user_example.py.
- Tables/standalone figure from retained summaries: render_results.py.

All paths below are relative to docs/program/evidence/2026-10-24/doc-01/:

| Evidence | Directory |
|---|---|
| Feature ledger: 123 requirements, 131 semantic rows, 27 clauses | 20261024T111005Z-audit-73ab3122 |
| Six companion checks | 20261024T111015Z-test-c1c77425 |
| Response HPO: 12 studies, 402 fitted artifacts | 20261024T111043Z-response-1e2f304c |
| Equilibrium NAS: 12 studies, 420 fitted artifacts | 20261024T111117Z-equilibrium-9eae69cb |
| Independent reconstruction of all 822 models and 24 studies | 20261024T111305Z-verify-bd58fa85 |

Each example retains results/summary.json, per-replicate data/declaration and
full-grid table, and per-method SQLite, checkpoint, models, report and summary.
Receipts bind driver inputs and unchanged qualified core source. Warnings and
failed preparation attempts remain retained; no trial failed during either
successful example. Completed resume used fresh objects in every study.

The response and equilibrium processes took 16.59 and 51.25 seconds. Those are
observed machine times, not promises. GP found all finite tuning minima, but
its dataset-303 NAS winner was less stable on final seeds. Independent numeric
checks passing does not certify that trained approximation as adequate. The
manual includes all 24 outcomes, search overhead and derivative limitations;
none supplies a superiority or real-bank effectiveness result.
