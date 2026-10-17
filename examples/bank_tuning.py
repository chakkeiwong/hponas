"""Self-contained bank-model workflows; no bank data or sibling imports."""
import argparse
import json
from pathlib import Path
import tempfile

from workloads.bank_prediction import prediction_profile
from workloads.bank_causal import causal_profile
from workloads.bank_inference import inference_profile
from workloads.bank_solvers import solver_profile
from workloads.bank_decisions import decision_profile
from workloads.bank_nas import nas_prediction_profile


def run(name, directory, *, budget=8, resume=False):
    profile=(nas_prediction_profile() if name=='nas_prediction' else
             decision_profile(name) if name in ('valuation','valuation_unidentified','wallet','allocation','allocation_uncertain') else
             solver_profile() if name=='solver' else inference_profile() if name=='inference' else
             causal_profile(overlap=name!='causal_overlap',identified=name!='causal_unidentified')
             if name in ('causal','causal_overlap','causal_unidentified') else prediction_profile(name))
    return profile.run(directory,budget=budget,resume=resume)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['ridge','bernoulli','censored','ar',
                        'causal','causal_overlap','causal_unidentified','inference','solver',
                        'valuation','valuation_unidentified','wallet','allocation','allocation_uncertain','nas_prediction'],default='ridge')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--budget',type=int,default=8)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if not 1<=args.budget<=32: parser.error('Budget must be in [1,32]')
    if args.resume and args.output_dir is None: parser.error('Resume requires the original output directory')
    destination=args.output_dir or Path(tempfile.mkdtemp(prefix='hponas-bank-'))
    output=run(args.profile,destination,budget=args.budget,resume=args.resume)
    print(json.dumps({'directory':str(destination),'profile':args.profile,
        'selection':output['report']['selection'],'evaluation':output['result']['evaluation']['outcome'],
        'final_assessments':output['final_assessments'],
        'scientific_acceptance':False},indent=2))


if __name__=='__main__': main()
