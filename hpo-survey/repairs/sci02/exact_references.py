"""Deterministic synthetic identities and bounded wallet precision planning."""
import math
import numpy as np


def points(value):
    x=np.asarray(value,dtype=float)
    if x.ndim<1 or x.shape[-1]!=2 or not np.isfinite(x).all():
        raise ValueError('Finite two-coordinate points required')
    return x


def banana_forward(z):
    z=points(z);x=z.copy()
    x[...,1]=z[...,1]+.35*(z[...,0]**2-1)
    if not np.isfinite(x).all():raise ValueError('Transform overflow')
    return x


def banana_inverse(x):
    x=points(x);z=x.copy()
    z[...,1]=x[...,1]-.35*(x[...,0]**2-1)
    if not np.isfinite(z).all():raise ValueError('Transform overflow')
    return z


def banana_log_density(x):
    z=banana_inverse(x)
    return -.5*np.sum(z*z,axis=-1)-math.log(2*math.pi)


def harmonic_flow(z,p,t):
    z,p=points(z),points(p)
    if z.shape!=p.shape or type(t) not in (int,float) or not math.isfinite(t):
        raise ValueError('Matched coordinates and finite flow time required')
    c,s=math.cos(t),math.sin(t)
    return c*z+s*p,-s*z+c*p


def quarter_period_reference(independent_standard_normal_momenta):
    """Caller supplies iid N(0,I) momenta; no RNG or chain is run here.

    At T=pi/2 the symbolic rotation has z_next=p. Assign directly instead of
    pretending floating cos(pi/2) is exactly zero. Then transform to banana.
    This function cannot verify that caller-provided values are random/iid.
    """
    return banana_forward(independent_standard_normal_momenta)


def half_width(n,alpha=.05,comparisons=6,range_width=6.3,look=None):
    """Hoeffding union bound conditional on frozen policies and iid outcomes.

    If a prospective sequential design is used, look k spends alpha/[k(k+1)].
    Union over comparisons and looks controls simultaneous error <=alpha.
    A caller must freeze the look schedule before seeing the outcomes.
    """
    if (type(n) is not int or n<1 or type(comparisons) is not int or comparisons<1
            or type(alpha) not in (int,float) or not 0<alpha<1
            or type(range_width) not in (int,float) or not math.isfinite(range_width)
            or range_width<=0 or (look is not None and (type(look) is not int or look<1))):
        raise ValueError('Invalid uncertainty design')
    a=alpha if look is None else alpha/(look*(look+1))
    return range_width*math.sqrt(math.log(2*comparisons/a)/(2*n))


def required_n(precision,alpha=.05,comparisons=6,range_width=6.3):
    if type(precision) not in (int,float) or not math.isfinite(precision) or precision<=0:
        raise ValueError('Positive finite precision required')
    scale=half_width(1,alpha,comparisons,range_width)
    return max(1,math.ceil((scale/precision)**2))
