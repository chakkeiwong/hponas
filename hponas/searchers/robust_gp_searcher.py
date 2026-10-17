"""Opt-in warped GP and noisy acquisition ensemble; no full HEBO parity claim."""
from copy import deepcopy
import hashlib
import importlib.metadata
import json

import numpy as np
import torch
from botorch.models import SingleTaskGP
from botorch.models.transforms.input import Warp
from botorch.models.utils.gpytorch_modules import get_covar_module_with_dim_scaled_prior
from botorch.optim.fit import fit_gpytorch_mll_scipy
from botorch.optim.core import OptimizationStatus
from botorch.sampling.normal import SobolQMCNormalSampler
from gpytorch.kernels import ScaleKernel
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.priors import LogNormalPrior

from hponas.encoding import as_knob_space
from hponas.gp_robustness import fit_output_power, noisy_ensemble, nondominated_indices
from hponas.searchers.gp_searcher import GPSearcher
from hponas.types import Result
from hponas.capabilities import SearcherCapabilities


class RobustGPSearcher(GPSearcher):
    """Serial continuous GP with bounded, auditable numerical approximations.

    Supports at most 16 unconditional continuous dimensions and 256 completed
    observations. Mixed spaces, batches, calibrated uncertainty and automatic
    default activation are outside this opt-in implementation's contract.
    """
    support = SearcherCapabilities(('continuous',), concurrent_proposals=False,
                                   max_dimensions=16, failed_observations=False)

    def __init__(self, search_space, seed=0, *, initial_random_samples=5,
                 candidate_count=64, posterior_samples=128, fit_iterations=50,
                 maximize=False):
        space = deepcopy(as_knob_space(search_space))
        if (not 1 <= space.dim <= 16 or any(k.kind != 'continuous' or k.condition for k in space.knobs)):
            raise ValueError('Robust GP requires 1 to 16 unconditional continuous axes')
        if type(seed) is not int or not 0 <= seed < 2**32 or type(maximize) is not bool:
            raise ValueError('Invalid robust GP seed or direction')
        for name, value, lower, upper in [('initial_random_samples', initial_random_samples, 2, 256),
            ('candidate_count', candidate_count, 4, 256), ('posterior_samples', posterior_samples, 4, 1024),
            ('fit_iterations', fit_iterations, 1, 200)]:
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('Invalid bounded '+name)
        super().__init__(space, seed, initial_random_samples=initial_random_samples, maximize=maximize)
        self.options = dict(seed=seed, initial_random_samples=initial_random_samples,
            candidate_count=candidate_count, posterior_samples=posterior_samples,
            fit_iterations=fit_iterations, maximize=maximize)
        self.last_diagnostics = None

    def validate_study_context(self, study_name):
        if self.maximize != self.options['maximize']:
            raise ValueError('Study direction must match robust GP construction')

    def validate_study_controls(self, max_concurrent, scheduler):
        if max_concurrent != 1 or scheduler is not None:
            raise ValueError('Robust GP supports serial studies without a scheduler')

    def observe(self, result):
        if (not isinstance(result, Result) or result.trial_id not in self.trials
                or result.status != 'completed' or not np.isfinite(result.objective_value)
                or abs(result.objective_value) > 1e100 or not np.isfinite(result.cost) or result.cost < 0):
            raise ValueError('Robust GP requires a registered finite completed report')
        self.search_space.validate_config(self.trials[result.trial_id].values)
        for old in self.history:
            if old.trial_id == result.trial_id:
                if old.to_dict() != result.to_dict():
                    raise ValueError('Conflicting robust GP report')
                return
        if len(self.history) >= 256:
            raise ValueError('Robust GP observation envelope exhausted')
        super().observe(deepcopy(result))

    def suggest(self):
        self.validate_study_context(None)
        before = deepcopy(self.rng.get_state()), self.n_suggestions, deepcopy(self.last_diagnostics)
        try:
            return super().suggest()
        except Exception:
            self.rng.set_state(before[0])
            self.n_suggestions, self.last_diagnostics = before[1:]
            raise

    def _suggest_impl(self):
        if len(self.history) >= 256:
            raise ValueError('Robust GP observation envelope exhausted')
        seed = (self.seed + self.n_suggestions) % 2**32
        torch.manual_seed(seed)
        self.n_suggestions += 1
        if len(self.history) < self.initial_random_samples:
            self.last_diagnostics = None
            return self._sample_random()
        x, y = self._prepare_training_data(self.history)
        values, power = fit_output_power(y[:, 0].numpy())
        if not self.maximize:
            values = -values
        target = torch.tensor(values[:, None], dtype=torch.float64)
        warp = Warp(d=x.shape[1], indices=list(range(x.shape[1])), bounds=self._get_bounds(),
            concentration0_prior=LogNormalPrior(0., .75), concentration1_prior=LogNormalPrior(0., .75))
        model = SingleTaskGP(x, target, input_transform=warp,
            covar_module=ScaleKernel(get_covar_module_with_dim_scaled_prior(
                ard_num_dims=x.shape[1], use_rbf_kernel=False))).double()
        fit = fit_gpytorch_mll_scipy(ExactMarginalLogLikelihood(model.likelihood, model),
            options={'maxiter': self.options['fit_iterations']}, timeout_sec=30)
        if fit.status == OptimizationStatus.FAILURE or not np.isfinite(fit.fval):
            raise RuntimeError('Robust GP fit failed: '+str(fit.message))
        # Iteration exhaustion is a disclosed bounded local fit, not convergence.
        if fit.message and 'timeout' in str(fit.message).lower():
            raise RuntimeError('Robust GP fit exceeded its time limit')
        model.eval()
        candidates = torch.quasirandom.SobolEngine(x.shape[1], scramble=True, seed=seed).draw(
            self.options['candidate_count']).double()
        query = torch.cat([x, candidates])
        with torch.no_grad():
            posterior = model.posterior(query, observation_noise=False)
            sampler = SobolQMCNormalSampler(torch.Size([self.options['posterior_samples']]), seed=seed)
            draws = sampler(posterior)[..., 0]
            mean = posterior.mean[:, 0].numpy()
            covariance = posterior.distribution.covariance_matrix.numpy()
            scores = noisy_ensemble(draws.numpy(), mean, covariance, len(x))
            front = nondominated_indices(scores)
            selected = int(self.rng.choice(front))
            tensor = lambda value: value.detach().cpu().numpy().tolist()
            self.last_diagnostics = {
                'train_x': tensor(x), 'raw_y': tensor(y[:, 0]), 'warped_y': tensor(target[:, 0]),
                'power': power, 'candidates': tensor(candidates), 'draws': tensor(draws),
                'normal_draws': tensor(sampler.base_samples),
                'sampling_root': tensor(posterior.distribution.scale_tril),
                'mean': mean.tolist(), 'covariance': covariance.tolist(),
                'scores': scores.tolist(), 'front': front.tolist(), 'selected': selected,
                'fit_status': fit.status.name, 'fit_message': str(fit.message),
                'warp_a': tensor(warp.concentration1), 'warp_b': tensor(warp.concentration0),
                'warp_eps': 1e-7, 'lengthscale': tensor(model.covar_module.base_kernel.lengthscale[0]),
                'outputscale': float(model.covar_module.outputscale),
                'noise': float(model.likelihood.noise[0]), 'constant_mean': float(model.mean_module.constant),
                'outcome_mean': float(model.outcome_transform.means[0, 0]),
                'outcome_std': float(model.outcome_transform.stdvs[0, 0]),
                'normalized_targets': tensor(model.train_targets)}
        return self._tensor_to_config(candidates[selected])

    @staticmethod
    def _runtime():
        return {name: importlib.metadata.version(name) for name in ['numpy', 'scipy', 'torch', 'botorch', 'gpytorch']}

    @staticmethod
    def _digest(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def get_state(self):
        payload = {'schema': 'robust_gp_v1', 'space': self.search_space.to_dict(),
            'options': self.options, 'runtime': self._runtime(), 'base': super().get_state(),
            'diagnostics': self.last_diagnostics}
        return json.loads(json.dumps({'payload': payload, 'sha256': self._digest(payload)}, allow_nan=False))

    def set_state(self, state):
        try:
            payload = state['payload']
            if (set(state) != {'payload', 'sha256'} or self._digest(payload) != state['sha256']
                    or payload['schema'] != 'robust_gp_v1' or payload['space'] != self.search_space.to_dict()
                    or payload['options'] != self.options or payload['runtime'] != self._runtime()):
                raise ValueError('Robust GP checkpoint contract differs')
            restored = type(self)(self.search_space, **self.options)
            GPSearcher.set_state(restored, deepcopy(payload['base']))
            if (restored.seed != self.seed or restored.maximize != self.maximize
                    or restored.initial_random_samples != self.initial_random_samples
                    or type(restored.n_suggestions) is not int or restored.n_suggestions < 0):
                raise ValueError('Robust GP checkpoint controls differ')
            history = restored.history
            restored.history = []
            for config in restored.trials.values():
                restored.search_space.validate_config(config.values)
            for report in history:
                restored.observe(report)
            restored.last_diagnostics = deepcopy(payload['diagnostics'])
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError('Malformed robust GP checkpoint') from exc
        self.__dict__.update(restored.__dict__)
