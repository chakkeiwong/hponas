"""Independent finite algebra for bank examples; never used by objectives."""
from fractions import Fraction as F
import math


def ridge_reference(ridge, center=0):
    slope=F(12)/(4+F(ridge))
    return {'slope':float(slope),'intercept':float(1+(2-slope)*center),
            'loss':float(15*(slope-2)**2)}


def probability_reference(alpha, *, censored=False):
    events,survival=(2,5) if censored else (1,3)
    p=F(events+alpha,events+survival+2*alpha)
    return {'p':float(p),'loss':-(events*math.log(float(p))+survival*math.log(float(1-p)))/4}


def ar_reference(ridge, train_end, score_times):
    # Geometric-series sum; independent of production's dot products over rows.
    s=F(4,3)*(1-F(1,4)**train_end)
    slope=s/(2*(s+F(ridge)))
    score=sum(F(1,4)**(t-1) for t in score_times)/len(score_times)
    return {'slope':float(slope),'loss':float((slope-F(1,2))**2*score)}


def causal_reference(ridge, alpha, *, training_groups=1):
    """Integrate conditional moments; do not fit production rows/regressions."""
    beta=F(6*training_groups)/(6*training_groups+F(ridge))
    mse=brier=effect=F(0)
    for x,e in [(-1,F(1,4)),(1,F(3,4))]:
        p=(8*training_groups*e+alpha)/(8*training_groups+2*alpha)
        m0=F(1,2)+beta*(x+F(1,2));m1=F(7,2)+beta*(x-F(1,2))
        y0=1+x;y1=3+x
        mse+=((1-e)*(1+(y0-m0)**2)+e*(1+(y1-m1)**2))/2
        brier+=(e*(1-p)**2+(1-e)*p*p)/2
        effect+=(m1-m0+e*(y1-m1)/p-(1-e)*(y0-m0)/(1-p))/2
    return {'loss':float(mse+brier),'outcome_mse':float(mse),
            'treatment_brier':float(brier),'effect':float(effect)}


def gaussian_sequence_reference(values, observation_variance):
    import numpy as np
    n=len(values);r=F(observation_variance)
    covariance=[[F(1,2)**abs(i-j)*(F(1,3)+F(2,3)*F(1,4)**min(i,j))+(r if i==j else 0)
                 for j in range(1,n+1)] for i in range(1,n+1)]
    matrix=np.array(covariance,dtype=float);y=np.array(values,dtype=float)
    sign,logdet=np.linalg.slogdet(matrix)
    if sign!=1: raise ValueError('Reference covariance is not positive definite')
    return float((n*math.log(2*math.pi)+logdet+y@np.linalg.solve(matrix,y))/2)


def leapfrog_reference(state, step_size, length):
    h=F(step_size);one=((1-h*h/2,h),(-h+h**3/4,1-h*h/2));matrix=((F(1),F(0)),(F(0),F(1)))
    for _ in range(length):
        matrix=tuple(tuple(sum(matrix[i][k]*one[k][j] for k in range(2)) for j in range(2)) for i in range(2))
    point=tuple(sum(matrix[i][j]*F(state[j]) for j in range(2)) for i in range(2))
    energy_change=(sum(v*v for v in point)-sum(F(v)**2 for v in state))/2
    return {'position':float(point[0]),'momentum':float(point[1]),
            'log_acceptance':float(min(0,-energy_change)),
            'determinant':matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0]}


def neural_reference(config, train, score_nodes, *, task='solver'):
    """70-digit scalar dual arithmetic and normal equations, no workload imports."""
    from decimal import Decimal as D, localcontext
    with localcontext() as context:
        context.prec=70
        def decimal(x):return D(str(x))
        def basis(x):
            x=decimal(x);width=config['width'];act=config['activation']
            def activate(value,derivative):
                if act=='square':return value*value,2*value*derivative
                e=(2*value).exp();v=(e-1)/(e+1)
                return v,(1-v*v)*derivative
            hidden=[activate(x+D(i)/width,D(1)) for i in range(width)]
            if config['depth']==2:
                total=sum(v for v,_ in hidden);gradient=sum(d for _,d in hidden)
                hidden=[activate(v/2+total/(4*width),d/2+gradient/(4*width)) for v,d in hidden]
            selected=[hidden[0]] if config['representation']==1 else [hidden[0],hidden[-1]]
            return [D(1)]+[v for v,_ in selected],[D(0)]+[d for _,d in selected]
        rows=[];targets=[]
        for row in train:
            value,derivative=basis(row['x'])
            if task=='solver':
                boundary=row['task']=='boundary'
                rows.append(value if boundary else [v/4 for v in derivative])
                targets.append(decimal(row['target']) if boundary else decimal(row['target'])/4)
            else:
                normalization=D(len(train)).sqrt()
                rows.append([v/normalization for v in value]);targets.append(decimal(row['target'])/normalization)
        n=config['representation']+1
        matrix=[[sum(row[i]*row[j] for row in rows)+(decimal(config['ridge']) if i==j and i else D(0))
                 for j in range(n)] for i in range(n)]
        rhs=[sum(row[i]*y for row,y in zip(rows,targets)) for i in range(n)]
        augmented=[row+[value] for row,value in zip(matrix,rhs)]
        for col in range(n):
            pivot=max(range(col,n),key=lambda i:abs(augmented[i][col]))
            augmented[col],augmented[pivot]=augmented[pivot],augmented[col]
            divisor=augmented[col][col]
            if not divisor: raise ValueError('Singular independent neural reference')
            augmented[col]=[v/divisor for v in augmented[col]]
            for i in range(n):
                if i!=col:
                    factor=augmented[i][col]
                    augmented[i]=[a-factor*b for a,b in zip(augmented[i],augmented[col])]
        coefficients=[row[-1] for row in augmented]
        predictions=[];derivatives=[]
        for node in score_nodes:
            values,gradient=basis(node)
            predictions.append(float(sum(a*b for a,b in zip(coefficients,values))))
            derivatives.append(float(sum(a*b for a,b in zip(coefficients,gradient))))
        return {'coefficients':[float(v) for v in coefficients],'values':predictions,'derivatives':derivatives}


def valuation_reference(alpha):
    p=F(2+alpha,7+2*alpha);q=1-p
    return {'npv':float(-100+60*q*F(10,11)+60*q*q*F(100,121)),
            'loss':-(2*math.log(float(p))+5*math.log(float(q)))/4,'hazard':float(p)}


def allocation_reference(shrinkage, *, uncertain=False):
    shrink=F(shrinkage);weight=F(3,5)-F(2,5)*shrink
    means=(F(2,25),F(3,100)) if uncertain else (F(1,10),F(1,20))
    # Expand the variance polynomial independently of production matrix code.
    variance=F(1,4)*weight*weight-F(1,10)*weight+F(1,10)
    utility=weight*means[0]+(1-weight)*means[1]-variance/2
    regret=F(1,8)*(weight-F(2,5))**2
    return {'weight':float(weight),'loss':float(-utility),'regret':float(regret)}
