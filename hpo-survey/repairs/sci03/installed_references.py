"""Deterministic identities and uncertainty checks. No data generation."""
import json
import math
from pathlib import Path
import sys
import numpy as np
from hponas_scientific_checks.exact_references import (banana_forward,banana_inverse,banana_log_density,
    harmonic_flow,quarter_period_reference,half_width,required_n)


def reject(fn):
    try:fn()
    except (ValueError,TypeError):return True
    raise AssertionError('Invalid reference input accepted')


def run(out):
    z=np.array([[a,b] for a in (-2.,0.,1.) for b in (-1.,0.,2.)]);p=z[::-1].copy()
    x=banana_forward(z)
    assert np.allclose(banana_inverse(x),z,atol=2e-15,rtol=0)
    assert np.allclose(banana_log_density(x),-.5*(z*z).sum(1)-math.log(2*math.pi),atol=2e-15,rtol=0)
    for t in (0.,.15,1.2,1.8,math.pi/2):
        q,m=harmonic_flow(z,p,t);back,backp=harmonic_flow(q,-m,t)
        assert np.allclose(back,z,atol=3e-15,rtol=0)
        assert np.allclose(backp,-p,atol=3e-15,rtol=0)
        assert np.allclose((q*q+m*m).sum(1),(z*z+p*p).sum(1),atol=1e-14,rtol=0)
    assert np.array_equal(quarter_period_reference(p),banana_forward(p))
    # 5-point Gauss-Hermite integrates degrees through nine in each input.
    # Only polynomial identities up to degree six are evaluated here.
    nodes,w=np.polynomial.hermite.hermgauss(5);nodes*=math.sqrt(2);w/=math.sqrt(math.pi)
    grid=np.array([[a,b] for a in nodes for b in nodes]);weight=np.array([a*b for a in w for b in w])
    values=banana_forward(grid)
    moments={'mean_x1':float(weight@values[:,0]),'mean_x2':float(weight@values[:,1]),
             'var_x1':float(weight@values[:,0]**2),'var_x2':float(weight@values[:,1]**2),
             'cross':float(weight@(values[:,0]*values[:,1])),
             'x1_squared_x2':float(weight@(values[:,0]**2*values[:,1])),
             'x2_cubed':float(weight@values[:,1]**3)}
    expected=[0,0,1,1+2*.35**2,0,2*.35,8*.35**3]
    assert np.allclose(list(moments.values()),expected,atol=2e-14,rtol=0)
    precision=[]
    for level in (.90,.95,.99):
        for epsilon in (.1,.05,.01):
            n=required_n(epsilon,1-level)
            assert half_width(n,1-level)<=epsilon*(1+1e-14)
            if n>1:assert half_width(n-1,1-level)>epsilon*(1-1e-14)
            precision.append({'coverage':level,'half_width':epsilon,'sufficient_n_per_pair':n})
    # Independent alpha-spending telescoping identity, not simulated coverage.
    assert abs(sum(1/(k*(k+1)) for k in range(1,10001))-(1-1/10001))<1e-14
    assert half_width(100,look=1)>half_width(100)
    controls={
        'nonfinite_transform':reject(lambda:banana_forward([0,float('nan')])),
        'wrong_dimension':reject(lambda:banana_forward([0,1,2])),
        'flow_shape':reject(lambda:harmonic_flow(z,p[0],.1)),
        'flow_nonfinite_time':reject(lambda:harmonic_flow(z,p,float('nan'))),
        'zero_sample':reject(lambda:half_width(0)),
        'boolean_sample':reject(lambda:half_width(True)),
        'invalid_alpha':reject(lambda:half_width(10,alpha=0)),
        'invalid_look':reject(lambda:half_width(10,look=0)),
        'zero_precision':reject(lambda:required_n(0)),
        'nonfinite_precision':reject(lambda:required_n(float('nan')))}
    result={'mechanics_passed':True,'scientific_status':'exact_synthetic_reference_and_prospective_wallet_preparation',
            'gaussian_quadrature_moments':moments,'precision_curve':precision,'controls':controls,
            'new_observations':0,'new_sampler_chains':0,'new_fits':0,
            'wallet_superiority_established':False,'existing_sampler_convergence_proved':False,
            'qualification':'Exact reference under declared ideal Gaussian assumptions; deterministic numerical implementation checks only.'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':run(Path(sys.argv[1]))
