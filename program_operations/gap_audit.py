#!/usr/bin/python3 -I
"""Fixed dependency-free entry to the source-qualified gap trace guard."""
import importlib.util
from pathlib import Path
BASE=Path('/home/ubuntu/workspace/hponas')
spec=importlib.util.spec_from_file_location('gap_trace',BASE/'tools/gap_trace.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
validate=module.validate
CLAUSES=module.CLAUSES
if __name__=='__main__':raise SystemExit(module.main())
