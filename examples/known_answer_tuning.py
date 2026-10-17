"""Small tuning problems whose answers can be reconstructed independently.

Run: python -m examples.known_answer_tuning --output /tmp/tuning-observations.json
"""
import argparse
from itertools import combinations
import json
from pathlib import Path

from workloads.tuning_models import gaussian_flow, quadratic, spline
from workloads.gaussian_hmc import metropolis, sample_gaussian
from workloads.harmonic_hamiltonian import fit_hamiltonian


def run():
    quadratics = [{"eta": i/40, **quadratic(i/40, 8)} for i in range(1, 26)]
    networks = [spline(list(knots)) for width in range(8) for knots in combinations(range(1, 8), width)]
    flows = [gaussian_flow(c) for c in [-.99, -.5, 0., .5, .99]]
    hamiltonians = [fit_hamiltonian(basis, ridge, frequency)
                    for frequency in [.5, 1., 2.]
                    for basis in [("q2",), ("p2",), ("q2", "p2"), ("q2", "qp", "p2")]
                    for ridge in [0., .0625, .25, 1., 4.]]
    chain = sample_gaussian(step_size=.5, steps=3, draws=32, warmup=8, seed=12)
    resonance, q = [], 2.
    for p in [-2., 1., 0., 2.]*4:
        row = metropolis(q, p, 1., 3, 1., .5)
        resonance.append(row)
        q = row["next_q"]
    return {"kind": "finite_tuning_workload_observations_v1", "quadratic": quadratics,
            "relu_architectures": networks, "exact_gaussian_flow": flows,
            "harmonic_hamiltonian": hamiltonians, "gaussian_hmc": chain,
            "resonance_counterexample": resonance,
            "claim": "Numerical observations for independent known-answer reconstruction",
            "v13_accepted": False, "general_optimizer_superiority": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run()
    if args.output:
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
    print(json.dumps({"quadratic_learning_rates": len(result["quadratic"]),
                      "relu_architectures": len(result["relu_architectures"]),
                      "gaussian_flow_settings": len(result["exact_gaussian_flow"]),
                      "hamiltonian_fits": len(result["harmonic_hamiltonian"]),
                      "hmc_gradient_evaluations": result["gaussian_hmc"]["gradient_evaluations"],
                      "v13_accepted": False}))


if __name__ == "__main__":
    main()
