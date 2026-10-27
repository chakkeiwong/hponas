"""Independent APP-02 synthetic wallet; no sibling repository dependencies."""
import itertools
import math
import time
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit, log_ndtr, ndtr

LOG2PI = math.log(2 * math.pi)
GRID = tuple(dict(zip(('mean', 'scale', 'incidence', 'ridge'), v)) for v in
             itertools.product(('intercept', 'linear', 'quadratic'), ('constant', 'linear'),
                               ('censored', 'mixture'), (0., .01)))
TRUE_CONFIG = dict(mean='quadratic', scale='linear', incidence='mixture', ridge=0.)
CAPS = np.array([.5, 1.5, 3.])
FEES = np.array([.015, .06, .15])

def features(x, cfg):
    x = np.asarray(x, dtype=float)
    blocks = [np.ones(len(x))]
    if cfg['mean'] != 'intercept': blocks.extend((x[:, 0], x[:, 1]))
    if cfg['mean'] == 'quadratic': blocks.extend((x[:, 0]**2, x[:, 0]*x[:, 1], x[:, 1]**2))
    mean = np.column_stack(blocks)
    scale = np.column_stack((np.ones(len(x)), x[:, 0])) if cfg['scale'] == 'linear' else np.ones((len(x), 1))
    incidence = np.column_stack((np.ones(len(x)), x)) if cfg['incidence'] == 'mixture' else np.empty((len(x), 0))
    return mean, scale, incidence

def parameters(theta, x, cfg):
    d, s, a = features(x, cfg); j = d.shape[1]; k = j + s.shape[1]
    mu = d @ theta[:j]; sigma = np.exp(s @ theta[j:k])
    eta = a @ theta[k:] if a.shape[1] else np.full(len(x), np.inf)
    return mu, sigma, eta

def truth(x):
    x = np.asarray(x)
    return (.25 + .55*x[:, 0] - .30*x[:, 1] + .35*x[:, 0]*x[:, 1],
            np.exp(-.60 + .30*x[:, 0]), .40 - .80*x[:, 0] + .50*x[:, 1])

def truth_theta():
    return np.array([.25, .55, -.30, 0., .35, 0., -.60, .30, .40, -.80, .50])

def log_parts(mu, sigma, eta):
    lp = log_expit(eta); lq = np.logaddexp(log_expit(-eta), lp + log_ndtr(-mu/sigma))
    return lp, lq

def objective(theta, x, wallet, cfg, penalized=True):
    d, s, a = features(x, cfg); j = d.shape[1]; k = j + s.shape[1]
    mu, sigma, eta = parameters(theta, x, cfg); p = expit(eta); lp, lq = log_parts(mu, sigma, eta)
    positive = wallet > 0; z = np.log1p(wallet); u = (z-mu)/sigma; t = -mu/sigma
    loss = np.where(positive, -lp + np.log(sigma) + .5*(LOG2PI+u*u) + z, -lq)
    ratio = np.exp(lp - .5*t*t - .5*LOG2PI - lq)
    gmu = np.where(positive, -u/sigma, ratio/sigma)
    gs = np.where(positive, 1-u*u, ratio*t)
    ga = np.where(positive, p-1, np.exp(lp+log_expit(-eta)+log_ndtr(-t)-lq))
    gradient = np.concatenate((d.T@gmu, s.T@gs, a.T@ga))/len(x)
    mask = np.ones(len(theta)); mask[0] = mask[j] = 0
    if a.shape[1]: mask[k] = 0
    ridge = cfg['ridge'] if penalized else 0.
    return float(loss.mean()+.5*ridge*np.dot(mask*theta, theta)), gradient+ridge*mask*theta

def bounds(cfg):
    d, s, a = features(np.zeros((1, 2)), cfg)
    return [(-5., 5.)]*d.shape[1] + [(-2., .7)] + [(-.8, .8)]*(s.shape[1]-1) + [(-6., 6.)]*a.shape[1]

def projected_gradient(theta, gradient, limits):
    g = np.array(gradient, copy=True)
    for i, (lo, hi) in enumerate(limits):
        if theta[i] <= lo+1e-8: g[i] = min(g[i], 0.)
        if theta[i] >= hi-1e-8: g[i] = max(g[i], 0.)
    return float(np.max(np.abs(g)))

def fit(cfg, x, wallet):
    start_time = time.monotonic(); d, s, a = features(x, cfg)
    beta = np.linalg.lstsq(d, np.log1p(wallet), rcond=None)[0]
    gamma = np.zeros(s.shape[1]); gamma[0] = -.5
    alpha = np.zeros(a.shape[1])
    if len(alpha): alpha[0] = 1.
    initial = np.concatenate((beta, gamma, alpha)); limits = bounds(cfg)
    rng = np.random.default_rng(7319); starts = [initial]+[initial+rng.normal(0, .35, len(initial)) for _ in range(2)]
    traces = []; candidates = []; work = 0
    for index, seed in enumerate(starts):
        seed = np.clip(seed, np.array(limits)[:, 0], np.array(limits)[:, 1])
        result = minimize(objective, seed, args=(x, wallet, cfg), jac=True, method='L-BFGS-B', bounds=limits,
                          options=dict(maxiter=800, ftol=2e-15, gtol=2e-8, maxls=40))
        value, grad = objective(result.x, x, wallet, cfg); residual = projected_gradient(result.x, grad, limits)
        valid = bool(np.isfinite(value) and np.all(np.isfinite(result.x)) and residual <= 1e-6)
        work += int(result.nfev)*len(x)
        traces.append(dict(start=index, objective=value, projected_gradient=residual, iterations=int(result.nit),
                           evaluations=int(result.nfev), scipy_success=bool(result.success), valid=valid, message=str(result.message)))
        if valid: candidates.append((value, index, result.x.copy(), residual))
    if not candidates: raise ValueError('No stationary wallet fit: '+str(traces))
    value, chosen, theta, residual = min(candidates, key=lambda v: (v[0], v[1]))
    return dict(config=cfg, theta=theta.tolist(), objective=value, projected_gradient=residual, selected_start=chosen,
                traces=traces, work=work, seconds=time.monotonic()-start_time,
                stationary_objective_spread=max(v[0] for v in candidates)-min(v[0] for v in candidates))

def empirical_loss(model, x, wallet):
    return objective(np.array(model['theta']), x, wallet, model['config'], penalized=False)[0]

def expected_nll(candidate, true):
    """Exact conditional expectation for the common exp(L)-1 censoring map."""
    mu, sigma, eta = candidate; mt, st, et = true; pt = expit(et)
    lp, lq = log_parts(mu, sigma, eta); _, lqt = log_parts(mt, st, et)
    tail = ndtr(mt/st); phi = np.exp(-.5*(mt/st)**2)/math.sqrt(2*math.pi)
    first = mt*tail+st*phi; second = (mt*mt+st*st)*tail+mt*st*phi
    return -np.exp(lqt)*lq+pt*((-lp+np.log(sigma)+.5*LOG2PI)*tail+
                              .5*(second-2*mu*first+mu*mu*tail)/(sigma*sigma)+first)

def capped_mean(parts, cap):
    mu, sigma, eta = parts; t0 = -mu/sigma; t1 = (np.log1p(cap)-mu)/sigma
    return expit(eta)*(np.exp(mu+.5*sigma*sigma)*(ndtr(t1-sigma)-ndtr(t0-sigma))
                       -(ndtr(t1)-ndtr(t0))+cap*ndtr(-t1))

def covariate_rule(order):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    x = np.array(list(itertools.product(nodes, repeat=2)))
    w = np.outer(weights, weights).reshape(-1)/4
    return x, w

def population_metrics(model, order=24):
    x, weights = covariate_rule(order); actual = truth(x); candidate = parameters(np.array(model['theta']), x, model['config'])
    risk = expected_nll(candidate, actual); oracle = expected_nll(actual, actual)
    allocations = np.column_stack([capped_mean(candidate, cap) for cap in CAPS])
    true_allocations = np.column_stack([capped_mean(actual, cap) for cap in CAPS])
    # Synthetic utility is mobilized external funds less a declared action fee.
    predicted_utility = np.column_stack((np.zeros(len(x)), allocations-FEES))
    true_utility = np.column_stack((np.zeros(len(x)), true_allocations-FEES))
    chosen = predicted_utility.argmax(axis=1); best = true_utility.max(axis=1)
    regret = best-true_utility[np.arange(len(x)), chosen]
    return dict(expected_nll=float(weights@risk), excess_nll=float(weights@(risk-oracle)),
                allocation_mae=float(weights@np.abs(allocations-true_allocations).mean(axis=1)),
                allocation_decision_regret=float(weights@regret))

def generate(seed, sizes=(768, 384, 512)):
    rng = np.random.default_rng(seed); result = {}
    for role, n in zip(('train', 'validation', 'final'), sizes):
        x = rng.uniform(-1, 1, (n, 2)); mu, sigma, eta = truth(x)
        latent = mu+sigma*rng.normal(size=n); active = rng.random(n)<expit(eta)
        wallet = np.where(active, np.maximum(np.expm1(latent), 0.), 0.)
        observed = rng.random(n)<.75 if role != 'final' else np.ones(n, dtype=bool)
        result[role] = dict(x=x, wallet=wallet, observed=observed, ids=[f'{seed}:{role}:{i}' for i in range(n)])
    return result

def observed_rows(data, roles):
    return (np.concatenate([data[r]['x'][data[r]['observed']] for r in roles]),
            np.concatenate([data[r]['wallet'][data[r]['observed']] for r in roles]))
