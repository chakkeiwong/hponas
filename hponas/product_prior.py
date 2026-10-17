"""Pinned NePS product laws using bounded direct inverse-CDF sampling.

The underlying continuous laws are explicit; their numerical implementation is
SciPy float64 inverse CDF, not an exact-real sampler. No finite candidate pool,
unbounded rejection or prior-to-uniform timeout fallback is used.
"""
from copy import deepcopy
from fractions import Fraction
import math

from scipy.stats import truncnorm

from hponas.encoding import as_knob_space


class ProductPrior:
    def __init__(self, space, default, *, confidence='medium', mutation_rate=Fraction(1,2),
                 mutation_std=0.25, mutation_attempts=50):
        self.space=deepcopy(as_knob_space(space))
        if (not self.space.knobs or len(self.space.knobs)>64
                or any(k.condition or k.transform not in {'none','log'} for k in self.space.knobs)):
            raise ValueError('PriorBand product supports at most 64 unconditional linear/log coordinates')
        if confidence not in {'low','medium','high'}:
            raise ValueError('Unknown prior confidence')
        if type(mutation_rate) not in (int,Fraction) or not 0<=mutation_rate<=1:
            raise ValueError('Exact mutation probability in [0,1] required')
        if type(mutation_std) not in (int,float) or not math.isfinite(mutation_std) or mutation_std<=0:
            raise ValueError('Positive finite normalized mutation standard deviation required')
        if type(mutation_attempts) is not int or not 1<=mutation_attempts<=1000:
            raise ValueError('Mutation attempts must be in [1,1000]')
        self.confidence=confidence
        self.mutation_rate=Fraction(mutation_rate)
        self.mutation_std=float(mutation_std)
        self.mutation_attempts=mutation_attempts
        self._validate_config(default)
        self.default=deepcopy(default)
        for knob in self.space.knobs:
            if knob.kind=='categorical':
                if (knob.transform!='none'
                        or any(type(v) not in (str,int,float) or (type(v) is float and not math.isfinite(v))
                               for v in knob.bounds)
                        or any(v in knob.bounds[:i] for i,v in enumerate(knob.bounds))):
                    raise ValueError('Categorical choices must be distinct finite scalars')
            else:
                low,high=self._bounds(knob,expanded=True)
                if not math.isfinite(high-low) or not high>math.nextafter(low,high):
                    raise ValueError('Numerical interval has no representable interior')

    def _validate_config(self, config):
        if type(config) is not dict or set(config)!={k.name for k in self.space.knobs}:
            raise ValueError('Every product coordinate must be declared exactly once')
        self.space.validate_config(config)
        for knob in self.space.knobs:
            value=config[knob.name]
            if type(value) is bool or (knob.kind=='ordinal' and type(value) is not int):
                raise ValueError('Boolean aliases and nonintegral integer values are unsupported')
            if knob.kind!='categorical' and (type(value) not in (int,float) or not math.isfinite(value)):
                raise ValueError('Finite numerical coordinate required')

    @staticmethod
    def _bounds(knob, *, expanded):
        low,high=knob.bounds
        if expanded and knob.kind=='ordinal':
            low,high=low-0.499999,high+0.499999
        if knob.transform=='log':
            if low<=0:
                raise ValueError('Log integer interval expansion requires a positive lower bound')
            low,high=math.log(low),math.log(high)
        return float(low),float(high)

    def _normal(self, knob, center, mode, *, expanded=True):
        low,high=self._bounds(knob,expanded=expanded)
        value=math.log(center) if knob.transform=='log' else center
        location=(value-low)/(high-low)
        scale=self.mutation_std if mode=='mutation' else {'low':.5,'medium':.25,'high':.125}[self.confidence]
        return truncnorm(-location/scale,(1-location)/scale,loc=location,scale=scale)

    @staticmethod
    def _open_uniform(rng):
        # Midpoints of the 52-bit uniform grid avoid infinite endpoint quantiles.
        return (rng.getrandbits(52)+0.5)/2**52

    @staticmethod
    def bernoulli(rng, probability):
        if probability==0:
            return False
        if probability==1:
            return True
        return rng.randrange(probability.denominator)<probability.numerator

    def quantile(self, name, probability, *, mode='prior', center=None):
        """Inverse CDF of one numerical coordinate, with original integer rounding."""
        knob=next((k for k in self.space.knobs if k.name==name),None)
        if knob is None or knob.kind=='categorical' or mode not in {'base','prior','mutation'}:
            raise ValueError('A declared numerical coordinate and sampling mode are required')
        if type(probability) not in (int,float) or not 0<probability<1:
            raise ValueError('A probability strictly inside (0,1) is required')
        center=self.default if center is None else center
        self._validate_config(center)
        unit=probability if mode=='base' else float(self._normal(knob,center[name],mode).ppf(probability))
        low,high=self._bounds(knob,expanded=True)
        value=low+(high-low)*unit
        if knob.transform=='log':
            value=math.exp(value)
        if knob.kind=='ordinal':
            return int(round(value))
        # Match the retained FloatParameter's endpoint clipping after exponentiation.
        return min(knob.bounds[1],max(knob.bounds[0],value))

    def integer_masses(self, name, *, mode='prior', center=None, max_cells=4096):
        """Numerical CDF-bin integrals, never substituted by center PDF values."""
        knob=next((k for k in self.space.knobs if k.name==name),None)
        if knob is None or knob.kind!='ordinal' or mode not in {'base','prior','mutation'}:
            raise ValueError('An integer coordinate and sampling mode are required')
        start,end=knob.bounds
        if type(max_cells) is not int or not 0<end-start+1<=max_cells:
            raise ValueError('Integer mass enumeration exceeds its declared cap')
        center=self.default if center is None else center
        self._validate_config(center)
        low,high=self._bounds(knob,expanded=True)
        edges=[0.0]
        edges += [(math.log(i+.5) if knob.transform=='log' else i+.5)-low for i in range(start,end)]
        edges[1:]=[edge/(high-low) for edge in edges[1:]]
        edges.append(1.0)
        distribution=None if mode=='base' else self._normal(knob,center[name],mode)
        cumulative=edges if distribution is None else [float(distribution.cdf(x)) for x in edges]
        return tuple(cumulative[i+1]-cumulative[i] for i in range(len(cumulative)-1))

    def log_score(self, config, center=None):
        """Original standardized-density score; it is not a Lebesgue density.

        Integer scoring uses unexpanded bounds, although sampling uses expanded
        bins. The reference omits both the normal scale and log Jacobian factors.
        """
        center=self.default if center is None else center
        self._validate_config(config)
        self._validate_config(center)
        total=0.0
        for knob in self.space.knobs:
            val=config[knob.name]
            if knob.kind=='categorical':
                multiplier={'low':2,'medium':4,'high':6}[self.confidence]
                total+=math.log((multiplier if val==center[knob.name] else 1)/(len(knob.bounds)-1+multiplier))
            else:
                low,high=self._bounds(knob,expanded=False)
                unit=((math.log(val) if knob.transform=='log' else val)-low)/(high-low)
                distribution=self._normal(knob,center[knob.name],'prior',expanded=False)
                scale={'low':.5,'medium':.25,'high':.125}[self.confidence]
                total+=float(distribution.logpdf(unit))+math.log(scale)
        if not math.isfinite(total):
            raise ValueError('Prior score is outside the finite numerical envelope')
        return total

    def _coordinate(self, knob, rng, mode, center):
        if knob.kind!='categorical':
            return self.quantile(knob.name,self._open_uniform(rng),mode=mode,center=center)
        choices=knob.bounds
        if mode=='mutation':
            choices=[x for x in choices if x!=center[knob.name]]
            return choices[rng.randrange(len(choices))]
        if mode=='base':
            return choices[rng.randrange(len(choices))]
        multiplier={'low':2,'medium':4,'high':6}[self.confidence]
        slot=rng.randrange(len(choices)-1+multiplier)
        for value in choices:
            slot-=multiplier if value==center[knob.name] else 1
            if slot<0:
                return value
        raise RuntimeError('Categorical draw escaped its support')

    def sample(self, rng, *, mode='prior', center=None):
        if mode not in {'base','prior','mutation'}:
            raise ValueError('Unknown sampling mode')
        center=self.default if center is None else center
        self._validate_config(center)
        for _ in range(self.mutation_attempts if mode=='mutation' else 1):
            config={}
            for knob in self.space.knobs:
                if mode=='mutation' and not self.bernoulli(rng,self.mutation_rate):
                    config[knob.name]=center[knob.name]
                else:
                    config[knob.name]=self._coordinate(knob,rng,mode,center)
            self._validate_config(config)
            if mode!='mutation' or config!=center:
                break
        return config

    def contract(self):
        return {'space':self.space.to_dict(),'default':deepcopy(self.default),'confidence':self.confidence,
                'mutation_rate':str(self.mutation_rate),'mutation_std':self.mutation_std,
                'mutation_attempts':self.mutation_attempts,'reference':'neps-3f7475b',
                'base_measure':'product-uniform-in-declared-linear/log-coordinates; expanded-rounding-for-integers',
                'score':'reference-standardized-density; unexpanded-integers; no-log-jacobian',
                'sampling':'scipy-truncnorm-f64-inverse-cdf; 52-bit-open-midpoints',
                'conditional_support':False}
