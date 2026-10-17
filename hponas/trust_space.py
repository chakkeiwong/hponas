"""Typed trust-region geometry and positive-definite mixed-space GP kernels."""
from copy import deepcopy
import json
import math

import numpy as np
import torch
from gpytorch.kernels import Kernel, MaternKernel
from gpytorch.priors import LogNormalPrior
from scipy.stats import qmc

from hponas.encoding import SpaceEncoder, as_knob_space


def config_key(config):
    return json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False)


class HammingKernel(Kernel):
    """exp(-sum_j 1[x_j != x'_j]/ell_j), invariant to category labels."""
    has_lengthscale=True

    def forward(self,x1,x2,diag=False,**params):
        if diag:
            difference=(x1!=x2).to(x1.dtype)
        else:
            difference=(x1.unsqueeze(-2)!=x2.unsqueeze(-3)).to(x1.dtype)
        return torch.exp(-(difference/self.lengthscale).sum(dim=-1))


class MixedKernel(Kernel):
    """Matérn-5/2 on numeric features times a categorical Hamming kernel.

    Conditional numerical coordinates embed as (active*value, active), and an
    inactive category has its own label. Each factor is positive definite; their
    product is positive definite by the Schur product theorem. No ordinal
    distances are assigned to categorical labels.
    """
    def __init__(self,n_numeric,n_categorical):
        super().__init__()
        if n_numeric+n_categorical<1:
            raise ValueError('A nonempty mixed kernel is required')
        self.n_numeric,self.n_categorical=n_numeric,n_categorical
        if n_numeric:
            self.numeric=MaternKernel(nu=2.5,ard_num_dims=n_numeric,
                active_dims=tuple(range(n_numeric)),
                lengthscale_prior=LogNormalPrior(math.sqrt(2)+.5*math.log(n_numeric),math.sqrt(3)))
        if n_categorical:
            self.categorical=HammingKernel(ard_num_dims=n_categorical,
                active_dims=tuple(range(n_numeric,n_numeric+n_categorical)))

    def forward(self,x1,x2,diag=False,**params):
        if not self.n_numeric:
            return self.categorical(x1,x2,diag=diag,**params)
        if not self.n_categorical:
            return self.numeric(x1,x2,diag=diag,**params)
        return self.numeric(x1,x2,diag=diag,**params)*self.categorical(x1,x2,diag=diag,**params)


class TrustSpace:
    def __init__(self,space):
        self.space=deepcopy(as_knob_space(space))
        self.encoder=SpaceEncoder(self.space)
        if not self.space.knobs or len(self.space.knobs)>64:
            raise ValueError('Trust regions support between 1 and 64 logical coordinates')
        self.numeric=[k for k in self.space.knobs if k.kind!='categorical']
        self.categorical=[k for k in self.space.knobs if k.kind=='categorical']
        self.n_numeric=sum(1+bool(k.condition) for k in self.numeric)
        for k in self.categorical:
            if (any(type(v) not in (str,int,float) or (type(v) is float and not math.isfinite(v)) for v in k.bounds)
                    or any(v in k.bounds[:i] for i,v in enumerate(k.bounds))):
                raise ValueError('Distinct finite categorical labels required')

    def validate(self,config):
        if type(config) is not dict or set(config)-{k.name for k in self.space.knobs}:
            raise ValueError('Only declared configuration keys are supported')
        if any(type(v) is bool for v in config.values()):
            raise ValueError('Boolean coordinate aliases are unsupported')
        self.space.validate_config(config)
        config_key(config)

    def features(self,config):
        self.validate(config)
        units=dict(zip([k.name for k in self.space.knobs],self.encoder.encode(config)))
        values=[]
        for knob in self.numeric:
            active=knob.name in config
            values.append(float(units[knob.name]) if active else 0.)
            if knob.condition:
                values.append(float(active))
        values.extend(float(k.bounds.index(config[k.name])+1) if k.name in config else 0.
                      for k in self.categorical)
        return values

    def logical_lengthscales(self,kernel):
        numeric=kernel.numeric.lengthscale.detach().cpu().reshape(-1).tolist() if self.numeric else []
        categorical=kernel.categorical.lengthscale.detach().cpu().reshape(-1).tolist() if self.categorical else []
        scales={}
        index=0
        for knob in self.numeric:
            scales[knob.name]=numeric[index]
            index+=1+bool(knob.condition)
        scales.update({k.name:v for k,v in zip(self.categorical,categorical)})
        return [scales[k.name] for k in self.space.knobs]

    def region(self,center,length,lengthscales):
        self.validate(center)
        if (type(length) not in (int,float) or not math.isfinite(length) or not 0<length<=2
                or len(lengthscales)!=len(self.space.knobs)
                or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in lengthscales)):
            raise ValueError('Valid region length and one positive scale per logical coordinate required')
        scales=dict(zip([k.name for k in self.space.knobs],lengthscales))
        units=dict(zip([k.name for k in self.space.knobs],self.encoder.encode(center)))
        mean_log=math.fsum(math.log(scales[k.name]) for k in self.numeric)/len(self.numeric) if self.numeric else 0.
        bounds={}
        for knob in self.numeric:
            log_side=math.log(length)+math.log(scales[knob.name])-mean_log
            if abs(log_side)>700:
                raise ValueError('Region anisotropy exceeds numerical range')
            side=math.exp(log_side)
            bounds[knob.name]=[max(0.,units[knob.name]-side/2),min(1.,units[knob.name]+side/2)]
        return {'numeric_bounds':bounds,'categorical_radius':min(len(self.categorical),max(1,math.ceil(length*len(self.categorical)))),
                'newly_active_numeric':'full_declared_domain','metric':'unweighted_categorical_hamming'}

    def contains(self,center,config,region):
        self.validate(config)
        if sum(center.get(k.name)!=config.get(k.name) for k in self.categorical)>region['categorical_radius']:
            return False
        units=dict(zip([k.name for k in self.space.knobs],self.encoder.encode(config)))
        for knob in self.numeric:
            if knob.name in center and knob.name in config:
                low,high=region['numeric_bounds'][knob.name]
                if not low<=units[knob.name]<=high:
                    return False
        return True

    def finite_configs(self,cap=4096):
        if type(cap) is not int or cap<1:
            raise ValueError('A positive finite-domain cap is required')
        if any(k.kind=='continuous' for k in self.space.knobs):
            return None
        configs=[{}]
        for knob in self.space.knobs:
            values=knob.bounds if knob.kind=='categorical' else range(knob.bounds[0],knob.bounds[1]+1)
            count=len(knob.bounds) if knob.kind=='categorical' else knob.bounds[1]-knob.bounds[0]+1
            next_configs=[]
            for config in configs:
                if knob.condition and config.get(knob.condition[0])!=knob.condition[1]:
                    next_configs.append(config)
                else:
                    if len(next_configs)+count>cap:
                        return None
                    next_configs.extend({**config,knob.name:value} for value in values)
            if len(next_configs)>cap:
                return None
            configs=next_configs
        return configs

    def candidates(self,center,length,lengthscales,rng,*,count=256,exclude=()):
        if type(count) is not int or not 1<=count<=4096:
            raise ValueError('Candidate cap must be in [1,4096]')
        region=self.region(center,length,lengthscales)
        excluded={config_key(c) for c in exclude}
        finite=self.finite_configs()
        if finite is not None:
            choices=[c for c in finite if config_key(c) not in excluded and self.contains(center,c,region)]
            if len(choices)>count:
                choices=[choices[int(i)] for i in rng.choice(len(choices),size=count,replace=False)]
            return choices,region,True
        dim=len(self.space.knobs)
        # One bounded Sobol block; actual typed points are filtered after projection.
        samples=qmc.Sobol(dim,scramble=True,seed=int(rng.integers(2**31))).random_base2(math.ceil(math.log2(4*count)))
        mask=rng.random(samples.shape)<=min(20/dim,1.)
        empty=np.flatnonzero(~mask.any(axis=1))
        if len(empty):
            mask[empty,rng.integers(dim,size=len(empty))]=True
        choices=[]
        for unit,changes in zip(samples,mask):
            config={}
            for j,knob in enumerate(self.space.knobs):
                if knob.condition and config.get(knob.condition[0])!=knob.condition[1]:
                    continue
                if not changes[j] and knob.name in center:
                    config[knob.name]=center[knob.name]
                    continue
                if knob.kind=='categorical':
                    config[knob.name]=knob.bounds[min(int(unit[j]*len(knob.bounds)),len(knob.bounds)-1)]
                    continue
                low,high=region['numeric_bounds'].get(knob.name,[0.,1.])
                if knob.name not in center:
                    low,high=0.,1.
                mapped=low+(high-low)*unit[j]
                lo,hi=(self.encoder._warp(v,knob.transform) for v in knob.bounds)
                value=lo+mapped*(hi-lo)
                if knob.transform=='log':
                    value=np.exp(value)
                elif knob.transform=='logit':
                    value=1/(1+np.exp(-value))
                value=float(np.clip(value,knob.bounds[0],knob.bounds[1]))
                config[knob.name]=int(round(value)) if knob.kind=='ordinal' else value
            self.validate(config)
            key=config_key(config)
            if key not in excluded and self.contains(center,config,region):
                choices.append(config)
                excluded.add(key)
                if len(choices)==count:
                    break
        return choices,region,False

    def initial_design(self,rng,*,count,exclude=()):
        """Fresh global design, with finite domains sampled without replacement."""
        if type(count) is not int or not 1<=count<=4096:
            raise ValueError('Initial design count must be in [1,4096]')
        seen={config_key(c) for c in exclude}
        finite=self.finite_configs()
        if finite is not None:
            remaining=[c for c in finite if config_key(c) not in seen]
            order=rng.permutation(len(remaining))[:count]
            return [remaining[int(i)] for i in order],not remaining
        result=[]
        for _ in range(4):
            block=qmc.LatinHypercube(len(self.space.knobs),seed=int(rng.integers(2**31))).random(count)
            for coordinates in block:
                config=self.encoder.decode(coordinates,sampling=True)
                key=config_key(config)
                if key not in seen:
                    result.append(config)
                    seen.add(key)
                if len(result)==count:
                    break
            if len(result)==count:
                break
        return result,False
