# Example support

These scripts are source-checkout examples; they are not included in the wheel.
The previously qualified maintained examples also run by absolute script path
outside the checkout after installing the wheel. The Tier-1 examples were qualified against the installed wheel on Python 3.12 in
`docs/program/evidence/2026-10-07/tier1-engineering-01/`; scientific acceptance remains separate. No script modifies `sys.path` to
silently select checkout library code.

For current interface behavior and scope, use the [product support reference](../docs/PRODUCT_SUPPORT.md).
The declared scalar/vector examples and current Local/Ray/Store repairs have
development evidence; their changed-source installation and scientific review
remain part of PRD-01. The complete banking-family examples are still BANK-01
work, and old fixture qualification does not establish application usefulness.

| File | Status and dependencies | Master owner |
|---|---|---|
| `declared_tuning.py` | Maintained declared scalar workflow; analytic reference, separate final evaluation, work reservations, model JSON artifacts and complete Store/export report. | PRD-01 |
| `spike_branin.py` | Maintained; core for `--executor local`, `ray` extra for `--executor ray` or default `both`. Full proposal/fidelity/value traces compared across executors. Analytic fidelity demonstrates orchestration, not efficiency. | PKG-01 |
| `spike_crash_recovery.py` | Maintained; core. Driver interruption, committed Store prefix and exact uninterrupted Sobol trace. This is not the separate kill-9 conformance test. | PKG-01 |
| `v14_day_one_walk.py` | Maintained; `rl` extra. Bounded real PPO, checkpoint/curve/Store persistence and separate protected evaluation. Integration evidence only. | PKG-01 |
| `v14_day_one_walk_fast.py` | Compatibility entry point to the same bounded PPO implementation. | PKG-01 |
| `known_answer_tuning.py` | Maintained development example; core. Quadratic, ReLU, Gaussian and Hamiltonian numerical observations with independent exact references. Run as a module; installed-wheel qualification passed; finite campaign acceptance is retained separately and is source-specific. | WL-01 |
| `multi_objective_tuning.py` | Maintained development example; core, plus Optuna for `--method nsgaii`. Real vector Study/Store execution on fitted ReLU networks; fixed metrics and raw observations. Installed-wheel qualification passed; finite V09/V10 acceptance is retained on the 2026-10-07 source. | T1-MO |
| `multifidelity_tuning.py` | Maintained development example; core. Fourteen bounded streaming/resume/restart/crash cases with exact quadratic references. Installed-wheel qualification passed; finite V06 acceptance is retained on the 2026-10-07 source. | T1-MF |
| `prior_tuning.py` | Maintained development example; core. Six categorical PriorBand/uniform diagnostics with actual quadratic training, exact mixtures and pending recovery. Installed-wheel qualification passed; finite V11 acceptance is retained on the 2026-10-07 source; broader prior claims remain unaccepted. | PRI-01 |
| `product_prior_tuning.py` | Maintained development example; core. Six integer/continuous PriorBand diagnostics in linear/log coordinates, real training and independently derived optima. Installed-wheel qualification passed; finite V11 acceptance is retained on the 2026-10-07 source. | PRI-01 |
| `trust_tuning.py` | Maintained development example; core. Seven sequential trust-region training cases, linear/log coordinates, direction, restart, pending recovery and finite exhaustion. Independent conditioned GP and correlated posterior-draw reconstruction; installed-wheel qualification passed; finite V04-T1 acceptance is retained on the 2026-10-07 source. | T1-TRUST |
| `cost_tuning.py` | Maintained development example; core. Four actual quadratic-training cases with variable physical work, independent Gaussian cost moments, cheap-first/cooling selection, pending recovery and budget stopping. Installed-wheel qualification passed; cost finite campaign acceptance is retained separately and is source-specific. | T1-COST |
| `hamiltonian_mo_example.py` | Maintained small quadratic-feature Hamiltonian fit; known derivative/energy answers and adverse near-constant dynamics. | WL-01 |
| `sampler_neutra_example.py` | Maintained actual learned tanh-coupling example with transformed leapfrog. Finite math only; no posterior calibration claim. | WL-01 |
| `finance_tuning.py` | Maintained declared two-asset vector Study/Store example; exact train/evaluation moments, 64 metered updates, complete report and explicit deterministic-known-answer final opt-out. | WL-01 / PRD-01 |
| `population_known_answer.py` | Maintained ten-update two-generation example; finite V08 acceptance is retained on the 2026-10-08 source. | T2-POP |
| `operations_known_answer.py` | Maintained local operations example; a metered diagonal quadratic proves physical updates match the durable ledger, then verifies Store/Study recovery through an immutable SQLite backup. Distributed service acceptance remains open. | OPS-01 |
| `warm_start_tuning.py` | Maintained actual synthetic-history and target training, rational within-study ranks, leakage refusal, pending recovery and scalar-power reconstruction. No empirical warm-start/default claim. | T1-WARM |

From the checkout:

```bash
python -m examples.spike_branin --executor local
python -m examples.spike_crash_recovery
python -m examples.known_answer_tuning --output /tmp/tuning-observations.json
JAX_PLATFORMS=cpu OMP_NUM_THREADS=2 python -m examples.v14_day_one_walk
```

The integration examples create and retain a unique run directory. Optional
`--output-dir` chooses its parent; existing files are preserved. The original
broken examples are preserved under `archive/program-2026-09-28/examples-before-pkg-01`.
The known-answer example uses an optional `--output` file and refuses to replace
an existing file.

Audited validation uses `python -m validation.run_validation_with_audit V14` from
the **full Git checkout**, with tests, examples, dependency files and protocols
available to its existing source fingerprint. A wheel alone cannot produce that
repository identity and is rejected before creating a campaign directory. The
installed API and integration examples remain usable without Git or the checkout.

See [supported workload contracts](../docs/WORKLOADS.md). All archived acceptance remains tied to its original source.
