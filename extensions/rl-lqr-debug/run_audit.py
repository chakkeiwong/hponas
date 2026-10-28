from pathlib import Path
import sys,json
from audit import main,ROOT,BASE
op,out=sys.argv[1],Path(sys.argv[2])
if not out.resolve().is_relative_to(BASE) or not out.is_dir():raise ValueError('Fixed output directory required')
if op=='audit':main(out)
elif op=='master-audit':
 from tools.program_state import check,validate
 from copy import deepcopy
 errors,view=check(ROOT)
 if errors:raise ValueError(errors)
 p=json.loads((ROOT/'docs/program/program.json').read_text())
 if any(s['state']!='complete' for s in p['continuation']['steps'] if s['id']!='GAP-01/FINAL-AUDIT'):raise ValueError('Required stage unfinished')
 false=deepcopy(p);next(s for s in false['continuation']['steps'] if s['id']=='RL-LQR-07/AUDIT')['state']='planned'
 if not validate(ROOT,program=false)[0]:raise ValueError('False completion accepted')
 result=dict(passed=True,new_training=0,work_items=len(p['work_items']),stages=len(p['continuation']['steps']),requirements=len(p['requirements']),false_completion_rejected=True,qualification='Source tracing and zero-training diagnosis only; repair effectiveness remains unestablished.')
 (out/'master-audit-result.json').write_text(json.dumps(result,indent=2)+'\n')
else:raise ValueError('Unknown fixed audit operation')
