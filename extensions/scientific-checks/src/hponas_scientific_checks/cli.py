"""Bounded local JSON interfaces; no model fitting, downloads or subprocesses."""
import argparse
import json
from pathlib import Path
import sys

MAX_INPUT_BYTES=8*1024*1024


def read_json(path):
    with Path(path).open('rb') as f:
        data=f.read(MAX_INPUT_BYTES+1)
    if len(data)>MAX_INPUT_BYTES:
        raise ValueError('Input exceeds 8 MiB')
    def bad(value):raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(data,parse_constant=bad)


def execute(operation,payload):
    if not isinstance(payload,dict):raise ValueError('JSON object required')
    if operation=='nas':
        from .nas_certificate import check_certificate
        return check_certificate(payload['model'],payload['paths'],seconds=120)
    if operation=='wallet':
        from .wallet import enclose
        return enclose(payload['selected'],payload['likelihood'],max_leaves=2048,seconds=150)
    if operation=='wallet-verify':
        from .wallet import verify_partition
        return verify_partition(payload['selected'],payload['likelihood'],payload['report'],seconds=180)
    if operation=='pi':
        import numpy as np
        from .pi_float32 import probability_of_improvement
        p=probability_of_improvement(np.asarray(payload['logits'],dtype=np.float32),
             np.asarray(payload['borders'],dtype=np.float32),payload['incumbent_loss'])
        return {'probabilities':p.tolist(),'scope':'Finite BarDistribution arithmetic only; not optimizer effectiveness or pretrained identity.'}
    if operation=='reference':
        from .exact_references import banana_forward,banana_inverse,banana_log_density
        x=banana_forward(payload['points'])
        return {'transformed':x.tolist(),'inverse':banana_inverse(x).tolist(),
                'log_density':banana_log_density(x).tolist(),'scope':'Deterministic transform; caller-supplied points are not certified independent draws.'}
    raise ValueError('Unsupported operation')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['nas','wallet','wallet-verify','pi','reference'])
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        # Refuse overwrite before doing expensive calculations.
        if args.output is not None and args.output.exists():
            raise ValueError('Output already exists; choose a new file')
        result=execute(args.operation,read_json(args.input))
        content=json.dumps(result,indent=2,allow_nan=False)+'\n'
        if args.output is None:sys.stdout.write(content)
        else:
            with args.output.open('x') as f:f.write(content)
        return 0 if result.get('status')!='NOT_VERIFIED' else 3
    except (ValueError,TypeError,KeyError,ArithmeticError,OSError) as exc:
        print(json.dumps({'status':'ERROR','message':str(exc)}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
