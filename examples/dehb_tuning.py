"""Tune gradient descent on a quadratic with an exact spectral answer."""
import json

import numpy as np

from hponas import DEHBController, Knob, LocalExecutor, SearchSpace


def run():
    space = SearchSpace([Knob('learning_rate', 'continuous', (.025, .625))])
    options = dict(seed=7, min_fidelity=1, max_fidelity=8, eta=2)
    controller = DEHBController(space, **options)
    executor = LocalExecutor()
    updates = 0

    def objective(values, fidelity):
        nonlocal updates
        state = np.array([1., 1.])
        rate = values['learning_rate']
        for _ in range(int(fidelity)):
            state -= rate * np.array([1., 3.]) * state
            updates += 1
        loss = float(state @ state / 2)
        expected = ((1-rate)**(2*int(fidelity)) + (1-3*rate)**(2*int(fidelity))) / 2
        if not np.isclose(loss, expected, atol=2e-12, rtol=2e-10):
            raise ValueError('Numerical training differs from the spectral answer')
        return {'value': loss, 'cost': fidelity}

    try:
        for index in range(50):
            trial = controller.ask()
            if index == 13:
                saved = json.loads(json.dumps(controller.state_dict()))
                controller = DEHBController(space, **options)
                controller.load_state_dict(saved)
                if controller.ask().to_dict() != trial.to_dict():
                    raise ValueError('Pending trial changed on recovery')
            controller.tell(executor.execute(trial, objective))
    finally:
        executor.shutdown()
    best = controller.best()
    ratio = (1/3)**(1/15)
    rate_star = (1+ratio)/(3+ratio)
    optimum = ((1-rate_star)**16+(1-3*rate_star)**16)/2
    return {'learning_rate': best['job']['values']['learning_rate'],
            'full_fidelity_loss': best['result']['objective_value'],
            'known_optimal_loss': optimum, 'gradient_updates': updates,
            'accounted_updates': sum(row['result']['cost'] for row in controller.history)}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
