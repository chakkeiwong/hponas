"""Actual self-contained ranked-history training and independent reconstruction."""
import argparse
import json
from pathlib import Path
import tempfile

from validation.warm_finite_contract import contract
from validation.warm_finite_producer import execute_slot
from validation.warm_finite_reference import verify_raw


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args(argv)
    if args.output_dir:
        args.output_dir.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='warm-start-example-',dir=args.output_dir))
    # A distinct exposed development setting; no official acceptance allocation.
    slot={**contract()['slots'][0],'id':'example','history_curvature':1.5,'target_curvature':2.5}
    raw=execute_slot(slot,directory/'training')
    report=verify_raw(slot,raw,directory/'training')
    report.update(directory=str(directory),scientific_acceptance=False)
    (directory/'raw.json').write_text(json.dumps(raw,indent=2)+'\n')
    (directory/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
