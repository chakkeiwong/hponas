"""Tiny real fixed-hidden networks; output weights are fitted, saved and reused."""
from copy import deepcopy
from itertools import product
import math

import numpy as np

CHOICES={'width':[2,4],'depth':[1,2],'activation':['square','tanh'],
         'representation':[1,2],'ridge':[0.,.0625]}
ARCHITECTURE_KEYS=('width','depth','activation','representation')


def configurations():
    return [dict(zip(CHOICES,values)) for values in product(*CHOICES.values())]


def build(config):
    if set(config)!=set(CHOICES) or any(type(config[k]) is bool or config[k] not in v for k,v in CHOICES.items()):
        raise ValueError('Unknown neural configuration')
    if any(type(config[k]) is not int for k in ('width','depth','representation')):
        raise ValueError('Integer neural dimensions required')
    width=config['width']
    layers=[{'weight':np.ones((width,1)).tolist(),'bias':(np.arange(width)/width).tolist()}]
    if config['depth']==2:
        layers.append({'weight':(.5*np.eye(width)+np.ones((width,width))/(4*width)).tolist(),
                       'bias':np.zeros(width).tolist()})
    return {'kind':'bank_fixed_hidden_network_v1','config':deepcopy(config),'layers':layers,
            'output':[0.]*(config['representation']+1),'domain':[-1.,1.]}


def validate_model(model, expected_config=None):
    if model.get('kind')!='bank_fixed_hidden_network_v1' or model.get('domain')!=[-1.,1.]:
        raise ValueError('Unknown network schema or domain')
    config=model['config'];template=build(config)
    if model['layers']!=template['layers']:
        raise ValueError('Hidden model arrays differ from declared constructor')
    if (len(model['output'])!=len(template['output'])
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in model['output'])):
        raise ValueError('Invalid fitted output coefficients')
    if expected_config is not None and config!=expected_config:
        raise ValueError('Network configuration differs')
    return True


def features(model, nodes):
    validate_model(model)
    x=np.asarray(nodes,dtype=float)
    if x.ndim!=1 or not np.all(np.isfinite(x)) or np.any(np.abs(x)>1):
        raise ValueError('Finite neural probes must lie in the declared domain [-1,1]')
    value=x[:,None];derivative=np.ones_like(value);count=0
    for layer in model['layers']:
        w=np.asarray(layer['weight']);b=np.asarray(layer['bias'])
        before=value@w.T+b;gradient=derivative@w.T
        count+=len(x)*(4*w.size+b.size)
        if model['config']['activation']=='square':
            value=before*before;derivative=2*before*gradient
        else:
            value=np.tanh(before);derivative=(1-value*value)*gradient
    selected=[0] if model['config']['representation']==1 else [0,value.shape[1]-1]
    return np.column_stack((np.ones(len(x)),value[:,selected])),np.column_stack((np.zeros(len(x)),derivative[:,selected])),int(count)


def evaluate(model, nodes):
    value,derivative,work=features(model,nodes);output=np.asarray(model['output'])
    return {'values':(value@output).tolist(),'derivatives':(derivative@output).tolist(),
            'hidden_affine_operations':work,'output_multiply_adds':int(4*len(nodes)*len(output)),
            'feature_scale':float(max(np.max(np.abs(value)),np.max(np.abs(derivative))))}


def measure(model):
    validate_model(model)
    hidden=sum(np.asarray(layer['weight']).size+len(layer['bias']) for layer in model['layers'])
    return {'parameters':int(hidden+len(model['output'])),'trainable_parameters':len(model['output']),
            'fixed_hidden_parameters':int(hidden)}


def fit(config, train, *, task='solver'):
    model=build(config);nodes=[r['x'] for r in train]
    values,derivatives,work=features(model,nodes)
    if task=='solver':
        # Mean squared normalized derivative residual plus boundary loss.
        # Four derivative rows: normalize target by 2, then sqrt(1/4).
        design=np.array([values[i] if r['task']=='boundary' else derivatives[i]/4 for i,r in enumerate(train)])
        target=np.array([r['target'] if r['task']=='boundary' else r['target']/4 for r in train])
    elif task=='prediction':
        design=values/math.sqrt(len(train));target=np.array([r['target'] for r in train])/math.sqrt(len(train))
    else:raise ValueError('Unknown neural training task')
    penalty=np.diag([0.]+[math.sqrt(config['ridge'])]*config['representation'])
    augmented=np.vstack((design,penalty));response=np.concatenate((target,np.zeros(len(penalty))))
    coefficients,_,rank,_=np.linalg.lstsq(augmented,response,rcond=None)
    if rank!=len(coefficients):raise ValueError('Rank-deficient output fit')
    condition=float(np.linalg.cond(augmented))
    if not math.isfinite(condition):raise ValueError('Nonfinite fit conditioning')
    model['output']=coefficients.tolist()
    return model,{'condition_number':condition,'coefficient_l1':float(np.sum(np.abs(coefficients))),
        'training_feature_scale':float(max(np.max(np.abs(values)),np.max(np.abs(derivatives)))),
        'normalized_training_loss':float(np.sum((design@coefficients-target)**2)),
        'training_task':task,'fits':1,'training_hidden_affine_operations':work}


def transfer(model, child_config):
    validate_model(model);child=build(child_config)
    if any(model['config'][key]!=child_config[key] for key in ARCHITECTURE_KEYS):
        raise ValueError('Incompatible architecture transfer requires a fresh fit')
    child['output']=list(model['output'])
    return child
