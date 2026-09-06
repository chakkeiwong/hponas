"""Fixtures for prior recovery tests."""

import numpy as np
from hponas.space import SearchSpace, Knob


# Branin function constants
BRANIN_OPTIMUM = 0.397887  # Known global minimum
BRANIN_BOUNDS = {"x1": (-5.0, 10.0), "x2": (0.0, 15.0)}


def branin_2d_space():
    """Standard 2D Branin configuration space."""
    return SearchSpace(
        knobs=[
            Knob(name="x1", kind="continuous", bounds=BRANIN_BOUNDS["x1"]),
            Knob(name="x2", kind="continuous", bounds=BRANIN_BOUNDS["x2"]),
        ]
    )


def evaluate_branin(config):
    """Evaluate Branin function (minimize)."""
    x1 = config["x1"]
    x2 = config["x2"]

    a = 1.0
    b = 5.1 / (4.0 * np.pi**2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8.0 * np.pi)

    term1 = a * (x2 - b * x1**2 + c * x1 - r)**2
    term2 = s * (1 - t) * np.cos(x1)
    term3 = s

    return term1 + term2 + term3


def create_good_prior(space):
    """Prior centered at known Branin optimum."""
    from hponas.priors import ensure_guarded
    from scipy.stats import norm

    # Branin has three global minima, use (-pi, 12.275)
    def gaussian_prior(config):
        x1 = config["x1"]
        x2 = config["x2"]
        p1 = norm.pdf(x1, loc=-np.pi, scale=1.0)
        p2 = norm.pdf(x2, loc=12.275, scale=1.0)
        return p1 * p2

    return ensure_guarded(gaussian_prior, space, alpha=0.95)


def create_wrong_prior(space):
    """Prior antipodal from optimum."""
    from hponas.priors import ensure_guarded
    from scipy.stats import norm

    # Place at opposite corner from optimum
    def gaussian_prior(config):
        x1 = config["x1"]
        x2 = config["x2"]
        p1 = norm.pdf(x1, loc=10.0, scale=1.0)
        p2 = norm.pdf(x2, loc=0.0, scale=1.0)
        return p1 * p2

    return ensure_guarded(gaussian_prior, space, alpha=0.95)


def create_mediocre_prior(space):
    """Prior off-center but reasonable support."""
    from hponas.priors import ensure_guarded
    from scipy.stats import norm

    # Place at midpoint of space
    def gaussian_prior(config):
        x1 = config["x1"]
        x2 = config["x2"]
        p1 = norm.pdf(x1, loc=2.5, scale=3.0)
        p2 = norm.pdf(x2, loc=7.5, scale=3.0)
        return p1 * p2

    return ensure_guarded(gaussian_prior, space, alpha=0.95)


def run_pibo_study(prior, budget, seed):
    """Run πBO study to budget, return best-so-far curve."""
    from hponas.searchers_gp import GPqLogEISearcher

    space = branin_2d_space()
    searcher = GPqLogEISearcher(space, prior_fn=prior, seed=seed)

    best_so_far = []
    incumbent = float('inf')

    for _ in range(budget):
        configs = searcher.propose(n=1)
        config = configs[0]
        obj = evaluate_branin(config)

        # observe expects trial_result dict with config, value, fidelity, cost
        trial_result = {
            "config": config,
            "value": -obj,  # GPqLogEISearcher maximizes, Branin minimizes
            "fidelity": None,
            "cost": None,
        }
        searcher.observe(trial_result)

        incumbent = min(incumbent, obj)
        best_so_far.append(incumbent)

    return np.array(best_so_far)


def run_priorband_study(scheduler_config, prior, budget, seed):
    """Run PriorBand with ASHA to budget, return best-so-far curve."""
    from hponas.searchers_priorband import PriorBandSampler
    from hponas.schedulers import ASHAScheduler

    space = branin_2d_space()
    sampler = PriorBandSampler(space, prior_fn=prior, seed=seed)
    scheduler = ASHAScheduler(scheduler_config)

    best_so_far = []
    incumbent = float('inf')
    trial_states = {}  # trial_id -> (config, fidelity, status)
    trial_counter = 0
    fidelity_consumed = 0.0

    while fidelity_consumed < budget:
        # Propose new trials
        while len([t for t in trial_states.values() if t[2] == "running"]) < 4:
            config = sampler.propose(rung_idx=0)
            trial_id = f"trial_{trial_counter}"
            trial_counter += 1
            trial_states[trial_id] = (config, scheduler_config.r_min, "running")

        # Evaluate running trials
        for trial_id, (config, fidelity, status) in list(trial_states.items()):
            if status != "running":
                continue

            obj = evaluate_branin(config)
            fidelity_consumed += fidelity

            decision = scheduler.report(trial_id, fidelity, obj)
            sampler.observe(config, obj, rung_idx=0)

            incumbent = min(incumbent, obj)
            best_so_far.append(incumbent)

            if decision == "stop":
                trial_states[trial_id] = (config, fidelity, "stopped")
            elif decision == "pause":
                next_fidelity = fidelity * scheduler_config.eta
                trial_states[trial_id] = (config, next_fidelity, "paused")
            else:  # continue
                trial_states[trial_id] = (config, fidelity, "running")

            if fidelity_consumed >= budget:
                break

        # Promote paused trials
        promotions = scheduler.promote()
        for trial_id, next_fidelity in promotions:
            if trial_id in trial_states:
                config = trial_states[trial_id][0]
                trial_states[trial_id] = (config, next_fidelity, "running")

    return np.array(best_so_far[:budget]) if len(best_so_far) >= budget else np.array(best_so_far)


def compute_regret(curve, optimal_value):
    """Compute cumulative regret from best-so-far curve."""
    return np.cumsum(curve - optimal_value)


def measure_prior_density_overlap(samples, prior, percentile=90):
    """Measure fraction of samples in high-prior-density region."""
    densities = np.array([prior(config) for config in samples])
    threshold = np.percentile(densities, percentile)
    return np.mean(densities >= threshold)


def config_distance(config1, config2):
    """Euclidean distance between two configs in normalized space."""
    space = branin_2d_space()

    # Normalize to [0, 1]
    def normalize(config):
        x1_norm = (config["x1"] - BRANIN_BOUNDS["x1"][0]) / (BRANIN_BOUNDS["x1"][1] - BRANIN_BOUNDS["x1"][0])
        x2_norm = (config["x2"] - BRANIN_BOUNDS["x2"][0]) / (BRANIN_BOUNDS["x2"][1] - BRANIN_BOUNDS["x2"][0])
        return np.array([x1_norm, x2_norm])

    vec1 = normalize(config1)
    vec2 = normalize(config2)

    return np.linalg.norm(vec1 - vec2)


def get_prior_mode(space, prior):
    """Get mode (peak) of prior distribution."""
    # For Gaussian priors created in this module, mode is at the mean
    # Sample and find highest density
    from hponas.space import SearchSpace

    rng = np.random.RandomState(42)
    samples = []
    for _ in range(1000):
        config = {}
        for knob in space.knobs:
            low, high = knob.bounds
            config[knob.name] = rng.uniform(low, high)
        samples.append(config)

    densities = [prior(s) for s in samples]
    mode_idx = np.argmax(densities)
    return samples[mode_idx]
