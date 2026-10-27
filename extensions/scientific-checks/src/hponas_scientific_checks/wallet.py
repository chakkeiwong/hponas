"""Outward population enclosures for the retained synthetic wallet law.

Real-arithmetic saved policies, not floating-point decision error certification.
CDF uses a positive series with a geometric remainder; see MATHEMATICS.md.
"""
from fractions import Fraction
import heapq
import math
import time
from mpmath.ctx_iv import MPIntervalContext

iv = MPIntervalContext()
iv.dps = 30
CAPS = (.5, 1.5, 3.)
FEES = (.015, .06, .15)
SCOPE = "Frozen real-arithmetic policy under the named synthetic uniform wallet generator only; not real-bank or floating-point inference evidence."


def exact(v):
    if isinstance(v, Fraction):
        return iv.mpf(v.numerator) / v.denominator
    if type(v) is float:
        if not math.isfinite(v):
            raise ValueError('Nonfinite constant')
        n, d = v.as_integer_ratio()
        return iv.mpf(n) / d
    if type(v) is int:
        return iv.mpf(v)
    raise ValueError('A finite real constant is required')


def hull(lo, hi):
    return iv.mpf([lo.a, hi.b])


def intersect(a, b):
    lo, hi = max(a.a, b.a), min(a.b, b.b)
    if lo > hi:
        raise ArithmeticError('Inconsistent interval bounds')
    return iv.mpf([lo, hi])


def cdf_point(z):
    """Enclose Phi at a singleton dyadic endpoint; no scipy dependency."""
    if z.a != z.b:
        raise ValueError('CDF endpoint must be singleton')
    if z < 0:
        return 1 - cdf_point(-z)
    if z == 0:
        return iv.mpf(1) / 2
    if z > 8:
        tail = iv.exp(-z*z/2) / (z * iv.sqrt(2*iv.pi))
        return iv.mpf([1-tail.b, 1])
    s = term = iv.mpf(1)
    zz = z*z
    # t_(n+1)/t_n = z^2/(2n+3). Future ratios decrease.
    for n in range(512):
        q = zz / (2*n+3)
        nxt = term*q
        if q.b < 1:
            tail = nxt / (1-q)
            if tail.b < iv.mpf('1e-25'):
                val = iv.mpf(1)/2 + z*iv.exp(-zz/2)/iv.sqrt(2*iv.pi)*hull(s, s+tail)
                return intersect(val, iv.mpf([0, 1]))
        s += nxt
        term = nxt
    raise ArithmeticError('CDF series resource bound')


def cdf(z):
    return hull(cdf_point(z.a), cdf_point(z.b))


def validate_model(model):
    if not isinstance(model, dict) or not isinstance(model.get('config'), dict):
        raise ValueError('Missing wallet model/config')
    c = model['config']
    if c.get('mean') not in ('intercept', 'linear', 'quadratic') or c.get('scale') not in ('constant', 'linear') or c.get('incidence') not in ('censored', 'mixture'):
        raise ValueError('Unsupported wallet configuration')
    nm = {'intercept':1, 'linear':3, 'quadratic':6}[c['mean']]
    ns = 1 if c['scale'] == 'constant' else 2
    na = 0 if c['incidence'] == 'censored' else 3
    t = model.get('theta')
    if not isinstance(t, list) or len(t) != nm+ns+na or any(type(x) not in (int,float) or not math.isfinite(x) for x in t):
        raise ValueError('Invalid wallet parameters')
    limits = [5]*nm + [2] + ([.8] if ns == 2 else []) + [6]*na
    if any(abs(v)>lim for v,lim in zip(t,limits)) or t[nm]>.7:
        raise ValueError('Parameters outside the retained bounded fitting contract')
    return c, [exact(v) for v in t], nm, ns


def parts(prepared, x, y):
    c, t, nm, ns = prepared
    f = [iv.mpf(1), x, y, x*x, x*y, y*y][:nm]
    mu = sum((v*w for v,w in zip(t[:nm],f)), iv.mpf(0))
    sigma = iv.exp(t[nm] + (t[nm+1]*x if ns == 2 else 0))
    p = 1/(1+iv.exp(-(t[nm+ns]+t[nm+ns+1]*x+t[nm+ns+2]*y))) if c['incidence']=='mixture' else iv.mpf(1)
    return mu, sigma, p


def truth(x,y):
    mu = exact(.25)+exact(.55)*x-exact(.30)*y+exact(.35)*x*y
    sigma = iv.exp(exact(-.60)+exact(.30)*x)
    p = 1/(1+iv.exp(-(exact(.40)-exact(.80)*x+exact(.50)*y)))
    return mu,sigma,p


def utilities(parameters):
    mu,sigma,p = parameters
    t0=-mu/sigma
    f0=cdf(t0); fs0=cdf(t0-sigma)
    multiplier=iv.exp(mu+sigma*sigma/2)
    result=[iv.mpf(0)]
    for cap,fee in zip(CAPS,FEES):
        cap,fee=exact(cap),exact(fee)
        t1=(iv.ln(1+cap)-mu)/sigma
        mean=p*(multiplier*(cdf(t1-sigma)-fs0)-(cdf(t1)-f0)+cap*cdf(-t1))
        result.append(intersect(mean,iv.mpf([0,cap.b]))-fee)
    return result


def possible_actions(u):
    best_lower=max(v.a for v in u)
    return [i for i,v in enumerate(u) if v.b>=best_lower]


def rectangle(path):
    b=[Fraction(-1),Fraction(1),Fraction(-1),Fraction(1)]
    for i,bit in enumerate(path):
        if bit not in '01':
            raise ValueError('Invalid partition path')
        j=2*(i%2);mid=(b[j]+b[j+1])/2
        b[j+1 if bit=='0' else j]=mid
    return b


def cover(paths):
    if not isinstance(paths,(list,tuple)) or not 1<=len(paths)<=8192 or any(not isinstance(p,str) or len(p)>40 or set(p)-set('01') for p in paths):
        raise ValueError('Invalid bounded binary partition')
    if len(set(paths))!=len(paths):
        raise ValueError('Duplicate leaves')
    seen=set(paths)
    if any(p[:i] in seen for p in paths for i in range(len(p))):
        raise ValueError('Overlapping leaves')
    if sum((Fraction(1,2**len(p)) for p in paths),Fraction())!=1:
        raise ValueError('Incomplete partition')
    return True


def cell(prepared, path):
    a,b,c,d=rectangle(path)
    x=hull(exact(a),exact(b));y=hull(exact(c),exact(d))
    true_u=utilities(truth(x,y))
    actions=[possible_actions(utilities(parts(m,x,y))) for m in prepared]
    us=[hull(min(true_u[i].a for i in act),max(true_u[i].b for i in act)) for act in actions]
    differences=[iv.mpf(0) if i==j else true_u[i]-true_u[j] for i in actions[0] for j in actions[1]]
    delta=hull(min(v.a for v in differences),max(v.b for v in differences))
    regret=[]
    for act in actions:
        vals=[]
        for i in act:
            ds=[iv.mpf(0) if i==j else true_u[j]-true_u[i] for j in range(4)]
            vals.append(hull(max(v.a for v in ds),max(v.b for v in ds)))
        regret.append(hull(min(v.a for v in vals),max(v.b for v in vals)))
    return us+[delta]+regret,actions


def endpoints(value):
    return [list(v) for v in value._mpi_]


def from_endpoints(raw):
    if not isinstance(raw,list) or len(raw)!=2:
        raise ValueError('Two exact endpoints required')
    def rational(t):
        if not isinstance(t,list) or len(t)!=4 or any(type(v) is not int for v in t):
            raise ValueError('Malformed mpf endpoint')
        s,m,e,b=t
        if s not in (0,1) or m<0 or b!=m.bit_length() or abs(e)>10000:
            raise ValueError('Invalid finite mpf endpoint')
        return Fraction((-1 if s else 1)*m)*(Fraction(2)**e)
    lo,hi=map(rational,raw)
    if lo>hi:raise ValueError('Reversed endpoints')
    return hull(exact(lo),exact(hi))


def summarize(leaves, reason, seconds):
    cover(list(leaves))
    total=[iv.mpf(0) for _ in range(5)]
    rows=[]
    for path,(values,actions) in sorted(leaves.items()):
        mass=exact(Fraction(1,2**len(path)))
        total=[a+mass*b for a,b in zip(total,values)]
        rows.append({'path':path,'actions':actions,'bounds':[endpoints(v) for v in values]})
    delta=total[2]
    return {'status':'ENCLOSED','sign':'POSITIVE' if delta.a>0 else ('NEGATIVE' if delta.b<0 else 'UNRESOLVED'),
            'stop_reason':reason,'seconds':seconds,'leaf_count':len(rows),'rows':rows,
            'quantities':['selected_utility','likelihood_utility','selected_minus_likelihood','selected_regret','likelihood_regret'],
            'bounds':[endpoints(v) for v in total],'display_bounds':[[float(v.a),float(v.b)] for v in total],
            'scope':SCOPE,'rounding':'mpmath interval dps=30; exact endpoints authoritative, display floats approximate'}


def enclose(selected, likelihood, *, max_leaves=2048, seconds=150):
    if type(max_leaves) is not int or not 1<=max_leaves<=8192 or type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=180:
        raise ValueError('Invalid finite resource limits')
    prepared=[validate_model(selected),validate_model(likelihood)]
    start=time.monotonic();leaves={'':cell(prepared,'')};queue=[]
    def push(path):
        v=leaves[path][0];m=2.**(-len(path))
        # Priority is scheduling only, never acceptance arithmetic.
        score=m*((float(v[2].b)-float(v[2].a))+1e-6*sum((float(z.b)-float(z.a)) for z in v))
        heapq.heappush(queue,(-score,path))
    push('');reason='leaf_limit'
    while len(leaves)<max_leaves:
        if time.monotonic()-start>=seconds:reason='time_limit';break
        _,path=heapq.heappop(queue)
        if len(path)>=40:reason='depth_limit';break
        left,right=path+'0',path+'1'
        l=cell(prepared,left);r=cell(prepared,right)
        # Parent stays until both children exist: budget stop never drops mass.
        del leaves[path];leaves[left]=l;leaves[right]=r;push(left);push(right)
    return summarize(leaves,reason,time.monotonic()-start)


def verify_partition(selected,likelihood,report,*,seconds=180):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=180:
        raise ValueError('Invalid replay bound')
    if not isinstance(report,dict) or not isinstance(report.get('rows'),list):
        raise ValueError('Missing partition rows')
    paths=[r['path'] for r in report['rows']];cover(paths)
    prepared=[validate_model(selected),validate_model(likelihood)]
    leaves={};start=time.monotonic()
    for row in report['rows']:
        if time.monotonic()-start>=seconds:
            return {'status':'NOT_VERIFIED','reason':'resource_limit'}
        values,actions=cell(prepared,row['path'])
        if row['actions']!=actions or row['bounds']!=[endpoints(v) for v in values]:
            raise ValueError('Altered partition bounds/actions')
        leaves[row['path']]=(values,actions)
    actual=summarize(leaves,'replayed',time.monotonic()-start)
    if report['bounds']!=actual['bounds'] or report['sign']!=actual['sign'] or report['leaf_count']!=len(paths):
        raise ValueError('Altered aggregation or sign')
    return {'status':'VERIFIED','leaf_count':len(paths),'sign':actual['sign'],'bounds':actual['bounds']}
