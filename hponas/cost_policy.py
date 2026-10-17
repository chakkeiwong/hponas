"""CArBO budget cooling, initial-design elimination and typed cost evidence.

Censoring assumptions are explicit. Spent work and information about a latent
completion duration are different quantities, and both remain in each record.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math

import numpy as np
import torch


def positive(value, label, *, zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (not zero and value == 0)):
        raise ValueError(label+' must be finite and '+('nonnegative' if zero else 'positive'))
    return float(value)


def cooling(spent, budget, initial_budget=0.):
    """CArBO Eq. 3: (total-spent)/(total-initial), clipped to [0,1]."""
    spent = positive(spent, 'Spent budget', zero=True)
    budget = positive(budget, 'Total budget')
    initial_budget = positive(initial_budget, 'Initial budget', zero=True)
    if initial_budget >= budget:
        raise ValueError('Initialization budget must be smaller than total budget')
    return min(1., max(0., (budget-spent)/(budget-initial_budget)))


def cheap_first(log_costs, distances):
    """Algorithm 1: alternate removing most expensive and closest candidates.

    Inputs use the same candidate order. Distances are to the nearest previous
    design point; with an empty design all distances must be +infinity. Ties
    remove the earliest remaining index. Return the surviving original index
    and the full elimination trace. Never remove the final candidate.
    """
    costs = np.asarray(log_costs, dtype=float)
    distances = np.asarray(distances, dtype=float)
    if (costs.ndim != 1 or not 1 <= len(costs) <= 4096 or distances.shape != costs.shape
            or not np.isfinite(costs).all() or np.isnan(distances).any()
            or (distances < 0).any() or (np.isinf(distances).any() and not np.isposinf(distances).all())):
        raise ValueError('Finite log costs and nonnegative matched distances required')
    remaining, removed = list(range(len(costs))), []
    while len(remaining) > 1:
        index = max(remaining, key=lambda i: costs[i])
        remaining.remove(index)
        removed.append({'index': index, 'reason': 'most_expensive'})
        if len(remaining) > 1:
            index = min(remaining, key=lambda i: distances[i])
            remaining.remove(index)
            removed.append({'index': index, 'reason': 'closest_to_design'})
    return remaining[0], removed


def cost_aware_acquisition(base, log_expected_cost, exponent, *, log_domain):
    """Differentiable EI/cost^alpha or log(EI)-alpha*log(expected cost).

    Domain is explicit; guessing from a class name is not a numeric contract.
    Costs of a serial q-batch must first be summed in their natural domain.
    """
    if type(log_domain) is not bool:
        raise ValueError('An explicit acquisition domain is required')
    exponent = positive(exponent, 'Cost exponent', zero=True)
    if exponent > 1 or not isinstance(base, torch.Tensor) or not isinstance(log_expected_cost, torch.Tensor):
        raise ValueError('Torch acquisition tensors and exponent in [0,1] required')
    if base.shape != log_expected_cost.shape or not torch.isfinite(log_expected_cost).all():
        raise ValueError('Expected-cost shape or numerical domain differs')
    if (torch.isnan(base).any() or torch.isposinf(base).any()
            or (not log_domain and (not torch.isfinite(base).all() or (base < 0).any()))):
        raise ValueError('Acquisition must be nonnegative EI or finite/negative-infinite log EI')
    if exponent == 0:
        return base
    return base-exponent*log_expected_cost if log_domain else base*torch.exp(-exponent*log_expected_cost)


@dataclass(frozen=True)
class CostRecord:
    trial_id: str
    spent: float
    duration: float | None
    kind: str
    cause: str
    unit: str
    accounting: str
    censor_assumption: str | None = None

    def __post_init__(self):
        if type(self.trial_id) is not str or not self.trial_id:
            raise ValueError('Cost evidence requires a trial identity')
        positive(self.spent, 'Spent work', zero=True)
        if self.unit not in {'wall_seconds', 'declared_work_units'}:
            raise ValueError('Unknown cost unit')
        if self.accounting not in {'measured', 'lower_bound_after_interruption'}:
            raise ValueError('Unknown work-accounting provenance')
        if self.kind not in {'complete', 'right_censored', 'unmodeled'}:
            raise ValueError('Unknown duration evidence kind')
        if self.kind == 'unmodeled':
            if self.duration is not None or self.censor_assumption is not None:
                raise ValueError('Unmodeled work cannot supply duration likelihood')
        else:
            positive(self.duration, 'Completion duration or censor lower bound')
            if self.duration > self.spent:
                raise ValueError('Duration evidence exceeds measured spent work')
            if self.accounting != 'measured':
                raise ValueError('Incomplete aggregate accounting is not one observed duration')
            if self.kind == 'right_censored':
                if self.cause != 'external_deadline' or self.censor_assumption != 'deadline_independent_given_config':
                    raise ValueError('Censor likelihood requires an explicit noninformative deadline assumption')
            elif self.censor_assumption is not None or self.cause != 'completed':
                raise ValueError('Completed durations cannot carry censor assumptions')

    def to_dict(self):
        return asdict(self)


def observation_record(result, *, unit='wall_seconds', timeout_assumption=None):
    """Classify measured work without interpreting arbitrary failure as censoring.

    External deadlines need executor provenance plus a separately declared
    conditional independence assumption. Objective-raised TimeoutError, quality
    stopping, invalid objectives and interrupted aggregate work are unmodeled.
    They continue to consume the budget and stay visible in calibration records.
    """
    execution = deepcopy(result.metadata.get('execution', {}))
    if unit == 'wall_seconds':
        if 'elapsed_seconds' not in execution:
            raise ValueError('Executor wall-clock duration is missing')
        spent = execution['elapsed_seconds']
    elif unit == 'declared_work_units':
        spent = result.cost
    else:
        raise ValueError('Unknown cost unit')
    positive(spent, 'Measured work', zero=True)
    if timeout_assumption not in {None, 'deadline_independent_given_config'}:
        raise ValueError('Unknown censoring assumption')
    accounting = execution.get('accounting', 'measured')
    cause = str(result.status)
    kind, duration, assumption = 'unmodeled', None, None
    if result.is_valid() and result.status == 'completed' and accounting == 'measured' and spent > 0:
        cause, kind, duration = 'completed', 'complete', float(spent)
    elif (result.status == 'timeout' and execution.get('censor_cause') == 'external_deadline'
          and timeout_assumption is not None and accounting == 'measured' and spent > 0):
        cause, kind, duration, assumption = 'external_deadline', 'right_censored', float(spent), timeout_assumption
    return CostRecord(result.trial_id, float(spent), duration, kind, cause, unit, accounting, assumption)
