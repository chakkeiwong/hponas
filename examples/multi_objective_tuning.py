"""Run bounded vector tuning on fitted ReLU networks with a known exact frontier.

Run from the checkout: python -m examples.multi_objective_tuning --output-dir /tmp/mo
This is a development example; V09/V10 comparative acceptance remains separate.
"""
import argparse
import json
from pathlib import Path
import tempfile

from hponas import (Knob, SearchSpace, LocalExecutor, MultiObjectiveStudy,
                    MultiObjectiveRandomSearcher, MultiObjectiveBayesSearcher, WrappedNSGAIISearcher)
from hponas.store import Store
from workloads.tuning_models import spline


OBJECTIVES = [{"name": "integrated_error", "direction": "min", "lower": 0., "upper": 1/128},
              {"name": "hidden_units", "direction": "min", "lower": 0., "upper": 7.}]
CONTRACT = {"objectives": OBJECTIVES, "constraints": {"hidden_units": 5}, "work_unit": "least_squares_output_fits"}


def objective(config):
    mask = config["architecture_id"]
    result = spline([i for i in range(1, 8) if mask & (1 << (i-1))])
    return {"objectives": {k: result[k] for k in ["integrated_error", "hidden_units"]},
            "constraints": {"hidden_units": result["hidden_units"]}, "work": 1}


def run(method, directory, budget=12):
    space = SearchSpace([Knob("architecture_id", "ordinal", (0, 127))])
    if method == "random":
        searcher = MultiObjectiveRandomSearcher(space, **CONTRACT, seed=13)
    elif method == "nsgaii":
        searcher = WrappedNSGAIISearcher(space, **CONTRACT, seed=13, population_size=4)
    else:
        searcher = MultiObjectiveBayesSearcher(space, **CONTRACT, seed=13, method=method,
                                               candidate_count=32, mc_samples=32, fit_maxiter=20)
    store = Store(directory / "study.sqlite")
    try:
        study = MultiObjectiveStudy(searcher, LocalExecutor(), objective, **CONTRACT,
                                    budget=budget, study_name=method, checkpoint_dir=directory, store=store, legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
        result = study.run().to_dict()
        result.update(method=method, scientific_acceptance=False, task="fixed_knot_relu_output_fit",
                      architecture_encoding="seven_bit_subset_id", acquisition_domain="bounded_candidate_set")
        with (directory / "observations.json").open("x") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
        return result
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["random", "qlognehvi", "chebyshev", "nsgaii"], default="random")
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    parser.add_argument("--budget", type=int, default=12)
    args = parser.parse_args()
    if not 4 <= args.budget <= 32:
        parser.error("The bounded development example requires a budget in [4,32]")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=args.method+"-", dir=args.output_dir))
    result = run(args.method, directory, args.budget)
    print(json.dumps({"directory": str(directory), "trials": result["n_trials"], "hypervolume": result["metrics"]["hypervolume"],
                      "fits": result["metrics"]["total_work"], "scientific_acceptance": False}))


if __name__ == "__main__":
    main()
