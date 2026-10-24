"""Read the unchanged DOC-01 runtime after execution; no scientific rerun."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

import hponas
import numpy
import scipy
import torch
import optuna

result={
    'kind':'doc01-runtime-readback',
    'meaning':'Post-execution readback in the same fixed interpreter/dependency path; no package installation or runtime mutation occurred during DOC-01.',
    'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
    'affinity':sorted(os.sched_getaffinity(0)),
    'environment':{k:os.environ.get(k) for k in ['PYTHONPATH','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','CUDA_VISIBLE_DEVICES']},
    'versions':{n:importlib.metadata.version(n) for n in ['numpy','scipy','torch','botorch','gpytorch','optuna','cloudpickle','matplotlib']},
    'origins':{m.__name__:m.__file__ for m in [hponas,numpy,scipy,torch,optuna]},
    'context_sources':[]}
for name in ['/home/ubuntu/workspace/FinMarketing/src/finmarketing/estimators/response.py',
             '/home/ubuntu/workspace/dsge_hmc/main-baseline/tests/fixtures/neural_solver_verification_linear.py']:
    result['context_sources'].append({'path':name,'sha256':hashlib.sha256(Path(name).read_bytes()).hexdigest(),
                                     'use':'Read-only conceptual context; not imported by companions'})
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
