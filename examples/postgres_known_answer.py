"""Native numerical Study with PostgreSQL state and session-fenced work.

Provide HPONAS_POSTGRES_DSN for a private initialized schema. The caller owns
database lifecycle. --ray uses the caller's initialized private cluster, or an
owned two-CPU local cluster. No external deployment is created by this example.
"""

import argparse
import json
import math
import os
from pathlib import Path

from hponas import LocalExecutor, RayExecutor, Study
from hponas.postgres import PostgresStore, PostgresWorkLedger
from hponas.searchers import RandomSearcher
from hponas.space import SearchSpace, Knob


def run(dsn, schema, output_dir, *, use_ray=False):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    study_id = "quadratic-" + output.name
    allocation = study_id + "-updates"
    space = SearchSpace([Knob("eta", "continuous", (0.125, 0.875))])
    with PostgresStore(dsn, schema=schema) as store:
        token = store.coordinator_token(study_id)

        def training(config, reporter):
            trial_id = reporter.trial.trial_id
            value = 1.0
            trace = []
            with PostgresWorkLedger(
                dsn, schema=schema, allocation=allocation, capacity=24
            ) as ledger:
                with (output / (trial_id + ".jsonl")).open("x") as raw:
                    for index in range(4):
                        event = trial_id + ":" + str(index)
                        if not ledger.charge(event, study_id, coordinator=token):
                            raise RuntimeError(
                                "Previously charged work cannot be executed again"
                            )
                        value -= 2 * config["eta"] * value
                        trace.append(value)
                        raw.write(
                            json.dumps(dict(index=index, value=value, event=event))
                            + "\n"
                        )
                        raw.flush()
                        os.fsync(raw.fileno())
                        ledger.complete(event, coordinator=token)
                        reporter(
                            (index + 1) / 4,
                            value * value,
                            cost=index + 1,
                            checkpoint={"update": index + 1, "value": value},
                        )
            return {"value": value * value, "cost": 4}

        executor = (
            RayExecutor(num_workers=2, max_retries=0, timeout=45)
            if use_ray
            else LocalExecutor()
        )
        study = Study(
            RandomSearcher(space, seed=13),
            executor,
            training,
            budget=6,
            max_concurrent=2,
            maximize=False,
            study_name=study_id,
            store=store,
        )
        result = study.run()
        state = store.peek_study_snapshot(study_id)
    # Raw trajectories are verified independently from the training recurrence.
    for tid, row in state["trials"].items():
        eta = row["config"]["values"]["eta"]
        trace = [
            json.loads(line)
            for line in (output / (tid + ".jsonl")).read_text().splitlines()
        ]
        assert len(trace) == 4
        for i, update in enumerate(trace):
            assert update["index"] == i and math.isclose(
                update["value"], (1 - 2 * eta) ** (i + 1), rel_tol=2e-12, abs_tol=2e-14
            )
        assert math.isclose(
            state["results"][tid]["objective_value"],
            (1 - 2 * eta) ** 8,
            rel_tol=2e-12,
            abs_tol=2e-14,
        )
    with PostgresWorkLedger(
        dsn, schema=schema, allocation=allocation, capacity=24
    ) as ledger:
        metrics = ledger.metrics()
    assert metrics["charged_units"] == metrics["completed_units"] == 24
    with PostgresStore(dsn, schema=schema) as store:
        # Completed work must remain complete even under a fresh coordinator.
        def forbidden(config):
            raise AssertionError("Completed training repeated")

        resumed = Study(
            RandomSearcher(space, seed=13),
            LocalExecutor(),
            forbidden,
            budget=6,
            max_concurrent=2,
            maximize=False,
            study_name=study_id,
            store=store,
        )
        resumed.load_checkpoint()
        assert resumed.run().best_value == result.best_value
    receipt = dict(
        passed=True,
        gradient_updates=24,
        reconstruction_updates=0,
        metrics=metrics,
        best_loss=result.best_value,
        known_optimal_eta=0.5,
        known_optimal_loss=0,
        regret=result.best_value,
        ray=use_ray,
        distributed_service_accepted=False,
    )
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="hponas")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--ray", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                os.environ["HPONAS_POSTGRES_DSN"],
                args.schema,
                args.output_dir,
                use_ray=args.ray,
            )
        )
    )


if __name__ == "__main__":
    main()
