"""Historical diagnostic: real PPO random/pathological baseline learning curves.

Full runs are expensive: V04-T0 has 5 seeds, V05 has 3, each with 50 evaluations
per arm. --smoke executes one short evaluation per arm and is INCONCLUSIVE.
"""

from pathlib import Path
import numpy as np
from hponas import Knob, SearchSpace, RandomSearcher
from hponas.persistence import atomic_json
from validation.evidence import digest

PATHOLOGICAL_CONFIG = {"learning_rate": 1e-5, "batch_size": 64, "entropy_cost": 0.1}


def campaign(validation_id, run_dir, smoke=False):
    from workloads.rl_routine import RLSettings, rl_routine

    run_dir = Path(run_dir)
    settings = (
        RLSettings.smoke()
        if smoke
        else RLSettings(max_timesteps=100_000, num_minibatches=32)
    )
    space = SearchSpace(
        [
            Knob("learning_rate", "continuous", (1e-5, 1e-2), transform="log"),
            Knob("batch_size", "ordinal", (64, 512)),
            Knob("entropy_cost", "continuous", (0.0, 0.1)),
        ]
    )
    seeds = [0] if smoke else list(range(5 if validation_id == "V04-T0" else 3))
    count = 1 if smoke else 50
    curves = []
    for seed in seeds:
        searcher = RandomSearcher(space, seed=seed)
        for arm in ("random", "pathological"):
            values, receipts = [], []
            for index in range(count):
                config = (
                    searcher.suggest().values
                    if arm == "random"
                    else dict(PATHOLOGICAL_CONFIG)
                )
                if smoke:
                    config.update(batch_size=64, width=8, depth=1)
                result = rl_routine(
                    {**config, "num_envs": 32},
                    seed=seed * 1000 + index,
                    settings=settings,
                    artifact_dir=run_dir / "policies",
                    trial_id=f"{arm}_{seed}_{index}",
                )
                values.append(result["value"])
                receipts.append(result)
                atomic_json(run_dir / f"{arm}_{seed}_trials.json", receipts)
            incumbent = np.maximum.accumulate(values)
            curves.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "values": values,
                    "incumbent": incumbent.tolist(),
                    "auc": float(np.trapezoid(incumbent) / len(incumbent))
                    if len(incumbent) > 1
                    else float(incumbent[0]),
                    "receipts": {
                        "path": str((run_dir / f"{arm}_{seed}_trials.json").resolve()),
                        "sha256": digest(run_dir / f"{arm}_{seed}_trials.json"),
                    },
                }
            )
    return {
        "validation_id": validation_id,
        "claim": "diagnostic_random_vs_pathological_ppo",
        "certifies_tier0": False,
        "schema_version": 1,
        "workload": "brax_ppo",
        "real_workload": True,
        "smoke": smoke,
        "n_trials": count,
        "seeds": seeds,
        "curves": curves,
        "random_aucs": [c["auc"] for c in curves if c["arm"] == "random"],
        "pathological_aucs": [c["auc"] for c in curves if c["arm"] == "pathological"],
    }
