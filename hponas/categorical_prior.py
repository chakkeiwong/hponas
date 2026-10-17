"""Exact counting-measure laws for NePS categorical priors and local mutation."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import math

from hponas.encoding import as_knob_space


class CategoricalPrior:
    """Pinned NePS default-confidence and 50-attempt mutation on a finite product.

    Each categorical coordinate mutates with probability 1/2 to a uniformly
    selected *other* category. All-unchanged attempts repeat at most 50 times;
    the final unchanged mass is retained exactly. Continuous and conditional
    products require different laws and are refused by this implementation.
    """

    def __init__(self, space, default, *, confidence='medium', mutation_rate=Fraction(1, 2),
                 mutation_attempts=50, max_cells=4096):
        self.space = deepcopy(as_knob_space(space))
        if not self.space.knobs or any(k.kind != 'categorical' or k.condition or k.transform != 'none'
                                       for k in self.space.knobs):
            raise ValueError('Categorical PriorBand requires unconditional categorical coordinates')
        if confidence not in {'low', 'medium', 'high'}:
            raise ValueError('Prior confidence must be low, medium or high')
        if type(mutation_rate) not in (int, Fraction) or not 0 <= mutation_rate <= 1:
            raise ValueError('Exact mutation probability in [0,1] required')
        if type(mutation_attempts) is not int or mutation_attempts < 1:
            raise ValueError('A positive mutation attempt cap is required')
        if type(max_cells) is not int or max_cells < 1:
            raise ValueError('A positive finite support cap is required')
        count = math.prod(len(k.bounds) for k in self.space.knobs)
        if count > max_cells:
            raise ValueError('Categorical support exceeds max_cells')
        for knob in self.space.knobs:
            if (any(type(v) not in (str, int, float) or (type(v) is float and not math.isfinite(v))
                    for v in knob.bounds)
                    or any(v in knob.bounds[:i] for i, v in enumerate(knob.bounds))):
                raise ValueError('Categorical choices must be distinct finite JSON scalars')
        if type(default) is not dict or set(default) != {k.name for k in self.space.knobs}:
            raise ValueError('One default for every coordinate is required')
        self.space.validate_config(default)
        if any(type(v) is bool for v in default.values()):
            raise ValueError('Boolean default aliases are unsupported')
        self.default = deepcopy(default)
        self.confidence, self.mutation_rate = confidence, Fraction(mutation_rate)
        self.mutation_attempts, self.max_cells = mutation_attempts, max_cells
        self.cells = [dict(zip([k.name for k in self.space.knobs], values))
                      for values in product(*(k.bounds for k in self.space.knobs))]
        self.default_index = self.cells.index(default)

    def prior_masses(self, center=None):
        center = self.default if center is None else center
        self.space.validate_config(center)
        multiplier = {'low': 2, 'medium': 4, 'high': 6}[self.confidence]
        return tuple(math.prod(Fraction(multiplier if cell[k.name] == center[k.name] else 1,
                                         len(k.bounds)-1+multiplier) for k in self.space.knobs)
                     for cell in self.cells)

    def mutation_masses(self, center):
        self.space.validate_config(center)
        same = (1-self.mutation_rate)**len(self.space.knobs)
        tail = same**self.mutation_attempts
        multiplier = (1-tail)/(1-same) if same != 1 else Fraction(0)
        masses = []
        for cell in self.cells:
            attempt = math.prod(1-self.mutation_rate if cell[k.name] == center[k.name]
                                else self.mutation_rate/(len(k.bounds)-1) for k in self.space.knobs)
            masses.append(tail if cell == center else multiplier*attempt)
        return tuple(masses)

    def contract(self):
        return {'space': self.space.to_dict(), 'default': deepcopy(self.default), 'confidence': self.confidence,
                'mutation_rate': str(self.mutation_rate), 'mutation_attempts': self.mutation_attempts,
                'max_cells': self.max_cells, 'envelope': 'neps-categorical-product-counting-v1'}
