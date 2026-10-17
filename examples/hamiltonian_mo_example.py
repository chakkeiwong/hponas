"""Known-answer Hamiltonian feature tuning; two explicit physical objectives."""
import json

from workloads.harmonic_hamiltonian import fit_hamiltonian


def run():
    rows = [fit_hamiltonian(basis, ridge=ridge) for basis, ridge in [
        (('q2',), 0), (('q2', 'p2'), 0), (('q2', 'qp', 'p2'), 0), (('q2', 'p2'), 1e12)]]
    return {'model': 'learned_quadratic_feature_hamiltonian', 'rows': rows,
            'known_optimal_coefficients': {'q2': 1, 'qp': 0, 'p2': 1},
            'scientific_acceptance': False}


if __name__ == '__main__':
    result = run()
    print(json.dumps({'model': result['model'], 'objectives': [
        {'basis': r['basis'], 'ridge': r['ridge'], 'prediction_error': r['prediction_error'],
         'true_energy_drift': r['true_energy_drift']} for r in result['rows']],
         'scientific_acceptance': False}, indent=2))
