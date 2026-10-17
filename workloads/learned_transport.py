"""Actual learned invertible tanh coupling for a known Gaussian pushforward.

Finite cubature training and numerical transitions do not establish sampling
calibration or mixing. The transform has unit determinant for every parameter.
"""
from numbers import Real
import math

import torch


def _real(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError('Finite real transport coordinate required')
    return float(value)


def _points(points):
    value = torch.as_tensor(points, dtype=torch.float64)
    if value.ndim != 2 or value.shape[1] != 2 or not 1 <= len(value) <= 4096 or not torch.isfinite(value).all():
        raise ValueError('Finite transport points must have shape (N,2), N <= 4096')
    return value


class TanhTransport(torch.nn.Module):
    def __init__(self, amplitude=0.0):
        super().__init__()
        self.amplitude = torch.nn.Parameter(torch.tensor(_real(amplitude), dtype=torch.float64))

    def forward(self, points):
        points = _points(points)
        return torch.stack([points[:, 0], points[:, 1]+self.amplitude*torch.tanh(points[:, 0])], dim=1)

    def inverse(self, points):
        points = _points(points)
        return torch.stack([points[:, 0], points[:, 1]-self.amplitude*torch.tanh(points[:, 0])], dim=1)

    def log_abs_det_jacobian(self, points):
        points = _points(points)
        return torch.zeros(len(points), dtype=points.dtype)


def target_energy(points, target_amplitude):
    points = _points(points)
    a = _real(target_amplitude)
    latent_second = points[:, 1]-a*torch.tanh(points[:, 0])
    return (points[:, 0]**2+latent_second**2)/2


def latent_energy(points, transform, target_amplitude):
    return target_energy(transform(points), target_amplitude)-transform.log_abs_det_jacobian(points)


def train(*, target_amplitude=1.0, learning_rate=1.0, iterations=4, initial_amplitude=0.0, checkpoint=None):
    target, rate, initial = map(_real, [target_amplitude, learning_rate, initial_amplitude])
    if not abs(target) <= 4 or not abs(initial) <= 4 or not 0 < rate <= 2:
        raise ValueError('Transport training exceeds the finite coordinate envelope')
    if type(iterations) is not int or not 0 <= iterations <= 32:
        raise ValueError('Transport fidelity must be an integer in [0,32]')
    nodes = torch.tensor([-1., 0., 1.], dtype=torch.float64)
    first, second = torch.meshgrid(nodes, nodes, indexing='ij')
    points = torch.stack([first.flatten(), second.flatten()], dim=1)
    identity = {'schema': 'tanh_coupling_cubature_v1', 'target_amplitude': target,
                'learning_rate': rate, 'initial_amplitude': initial,
                'cubature_points': points.tolist(), 'cubature_weights': [1/9]*9,
                'work_unit': 'one full nine-point autograd update',
                'loss': 'mean target energy minus unit log determinant; fixed symmetric cubature'}
    completed, amplitude = 0, initial
    if checkpoint is not None:
        if (not isinstance(checkpoint, dict) or set(checkpoint) != {'identity', 'updates', 'amplitude'}
                or checkpoint['identity'] != identity or type(checkpoint['updates']) is not int
                or not 0 <= checkpoint['updates'] <= iterations):
            raise ValueError('Transport checkpoint identity/fidelity differs')
        completed, amplitude = checkpoint['updates'], _real(checkpoint['amplitude'])
        curvature = 2*math.tanh(1)**2/3
        expected = target+(initial-target)*(1-rate*curvature)**completed
        if abs(amplitude-expected) > 2e-12:
            raise ValueError('Transport checkpoint differs from training trajectory')
    transform = TanhTransport(amplitude)
    trace = []
    for index in range(completed, iterations):
        transform.zero_grad(set_to_none=True)
        loss = latent_energy(points, transform, target).mean()
        loss.backward()
        gradient = float(transform.amplitude.grad)
        if not torch.isfinite(transform.amplitude.grad):
            raise ValueError('Nonfinite transport gradient')
        with torch.no_grad():
            transform.amplitude.add_(transform.amplitude.grad, alpha=-rate)
        trace.append({'update': index+1, 'loss_before': float(loss.detach()),
                      'gradient': gradient, 'amplitude': float(transform.amplitude.detach())})
    amplitude = float(transform.amplitude.detach())
    return {'method': 'learned_unit_jacobian_tanh_coupling', 'task': identity,
            'amplitude': amplitude, 'loss': float(latent_energy(points, transform, target).mean().detach()),
            'trace': trace, 'transformed_points': transform(points).detach().tolist(),
            'incremental_updates': iterations-completed, 'total_updates': iterations,
            'checkpoint': {'identity': identity, 'updates': iterations, 'amplitude': amplitude},
            'scientific_acceptance': False, 'calibration_or_mixing_accepted': False}


def leapfrog(position, momentum, *, amplitude, target_amplitude, step_size, steps):
    rate = _real(step_size)
    if not 0 < rate <= 1 or type(steps) is not int or not 1 <= steps <= 32:
        raise ValueError('Bounded transport integrator coordinates required')
    q, p = _points([position]), _points([momentum]).clone()
    transform = TanhTransport(amplitude)
    def gradient(value):
        value = value.detach().requires_grad_(True)
        return torch.autograd.grad(latent_energy(value, transform, target_amplitude).sum(), value)[0]
    for _ in range(steps):
        p -= rate*gradient(q)/2
        q = (q+rate*p).detach()
        p -= rate*gradient(q)/2
    return {'position': q[0].tolist(), 'momentum': p[0].tolist(),
            'gradient_evaluations': 2*steps,
            'transformed_position': transform(q)[0].detach().tolist(),
            'method': 'leapfrog_on_learned_transport_target', 'scientific_acceptance': False}
