"""Private operation dispatch; invoke only through the bounded exact runner."""
import json
from pathlib import Path
import sys
import torch
from studies import save,run_family

def main():
    operation=sys.argv[1];out=Path(sys.argv[2]);torch.set_num_threads(1)
    if operation=='controls':
        from controls import run_controls
        result=run_controls();save(out/'controls.json',result)
    elif operation in ('forecast','wallet','policy','nas','transport'):result=run_family(operation,out/'results')
    elif operation=='verify':
        from verification import verify_all
        result=verify_all();save(out/'verification.json',result)
    elif operation=='synthesis':
        from reporting import synthesize
        result=synthesize(out)
    elif operation=='audit':
        from reporting import audit
        result=audit(out)
    else:raise ValueError('Unknown operation')
    print(json.dumps(result if operation=='controls' else {'operation':operation,'completed':True}),flush=True)

if __name__=='__main__':main()
