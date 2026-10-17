"""Finite Gaussian native-tuner handoff; retain every freshly verified pair."""
import argparse
import json
from pathlib import Path
import tempfile

from workloads.bank_inference import native_handoff, save_handoff


def run(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    result=native_handoff()
    path=save_handoff(directory/'handoff.json',result)
    return {'artifact':path,'result':result}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    output=run(args.output_dir or Path(tempfile.mkdtemp(prefix='hponas-handoff-')))
    print(json.dumps({'artifact':output['artifact'],'verified_pairs':output['result']['verified_pairs'],
                      'posterior_convergence':'not_assessed','scientific_acceptance':False},indent=2))
