"""Train a known-answer neural transport and check a transformed transition.

This is finite learned-coupling conformance. It does not estimate ESS or claim
posterior calibration. Ordinary-HMC diagnostics remain in known_answer_tuning.
"""
import json

from workloads.learned_transport import train, leapfrog


def run():
    trained = train(target_amplitude=1, learning_rate=2, iterations=8)
    transition = leapfrog([0.7, -1.25], [-0.3, 0.5], amplitude=trained['amplitude'],
                          target_amplitude=1, step_size=0.125, steps=4)
    return {'training': trained, 'transition': transition,
            'known_optimal_amplitude': 1, 'scientific_acceptance': False}


if __name__ == '__main__':
    result = run()
    print(json.dumps({'amplitude': result['training']['amplitude'],
                      'known_optimal_amplitude': result['known_optimal_amplitude'],
                      'training_updates': result['training']['total_updates'],
                      'transition': result['transition'], 'scientific_acceptance': False}, indent=2))
