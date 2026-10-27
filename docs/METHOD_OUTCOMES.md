# Method implementation and research outcomes

18 October 2026. Current guidance for GAP-01/TRANSFER-DISPOSITIONS. Original
roadmap labels and frozen results remain historical records; an accounted-for
disposition is not evidence that a method is implemented. The structured
requirement IDs below are in [the program register](program/program.json).

| Method and original requirement | Current outcome | Evidence and boundary |
|---|---|---|
| PBT — REQ-ch06-01 | Implemented, bounded local | `hponas/population.py`; retained V13 finite qualification. Model-neutral local adapters have current-source finite qualification; no distributed training claim. |
| PB2-Mix — REQ-roadmap-13, REQ-ch06-02 | Implemented, bounded local | Retained V13 population controllers; categorical/continuous schedules within the declared fixture contract. |
| BG-PBT — REQ-roadmap-13, REQ-ch06-03 | Implemented, bounded local | Retained V13 architecture lineage/transfer controls; not arbitrary topology NAS. |
| Large-parallel RL — REQ-ch09-02 | Finite local controller only | V13's finite-MDP evidence does not establish large distributed RL capacity or effectiveness. |
| Differential evolution/DEHB — REQ-ch03-05, REQ-roadmap-14, REQ-ch05-04 | Implemented, bounded finite | `hponas/dehb.py`; retained V07 qualification. General optimizer superiority is unestablished. |
| Selected GP robustness — REQ-roadmap-16 | Implemented, narrow opt-in | `hponas/searchers/robust_gp_searcher.py`; retained V08 mathematical qualification. Declared repeated Study use is refused where failure support is absent. |
| Neural transport — REQ-ch09-03 | Small trainable coupling fixture implemented | Retained V05 density/Jacobian/correction evidence; general posterior calibration and application benefit remain unestablished. |
| Ranked warm initialization | Implemented, opt-in | `hponas/warm_start.py`; transfers configurations and reevaluates on target. Retained V12 finite evidence is not an empirical speedup result. |
| RGPE — REQ-ch08-04 | Implemented bounded variant; current-source finite qualification passed | `hponas/rgpe.py`; actual fixed-kernel rank-weighted GP ensemble after ranked initialization, with target LOO loss and equal tie splitting. [Support and recovery](WARM_START.md); Current-source qualification and the final independent GAP-01/FINAL-AUDIT have passed. |
| Pretrained ifBO — REQ-roadmap-15, REQ-ch05-06 | Feasibility FAIL; V15b integration cancelled | [Frozen V15a result](../validation/artifacts/V15a/20261008_finite_ifbo_01/results.json), [retained diagnosis](program/evidence/2026-10-08/tier3-feasibility-01/retained-diagnosis.json). Two cases fail the prespecified float32 PI envelope. No favorable rerun, threshold change, integration or default activation is authorized. |
| SAASBO — REQ-ch04-07 | Not implemented; watchlist | New source, bounded protocol and objective evidence would be required; ordinary GP support is not SAASBO. |
| SMAC product integration — REQ-ch04-08 | Not implemented; watchlist | A reference dependency used by an experiment does not create a maintained product adapter. |
| FIRE-PBT — REQ-ch06-04 | Not implemented; watchlist | Local PBT/PB2/BG-PBT does not implement FIRE-PBT. |
| MF-PBT — REQ-ch06-04 | Not implemented; watchlist | Fidelity scheduling and population support separately do not implement MF-PBT. |
| IPBT — REQ-ch06-04 | Not implemented; watchlist | No inference from generic population interfaces. |
| SEARL — REQ-ch06-04 | Not implemented; watchlist | No inference from finite RL fixtures. |
| MORBO — REQ-ch07-06 | Not implemented; watchlist | Joint multi-objective EI and scalar trust regions do not implement MORBO. |
| Hypervolume knowledge gradient — REQ-ch07-06 | Not implemented; watchlist | qLogNEHVI is a different acquisition rule. |
| Broader PFNs — REQ-ch08-05 | Not implemented; watchlist | The terminal ifBO experiment does not establish a general pretrained-surrogate interface. |
| CARBS — REQ-roadmap-17, REQ-ch08-07 | Not implemented; watchlist | A cost predictor, cost-aware EI or finite Pareto front is not the CARBS method. |
| muP/scaling-law methods — REQ-ch08-08 | Not implemented; watchlist | Architecture coordinates alone do not implement scaling-law transfer. |

The watchlists are retained research outcomes, not outstanding mandatory
implementations in GAP-01. RGPE's previously omitted implementation obligation
is explicitly restored in that program. None of these finite outcomes establishes
empirical bank usefulness, posterior convergence, unattended production safety
or a universal best optimizer. Frozen accepted packages remain attached to their
original source; current-source qualification cannot be inherited from them.
