"""Zero-training correction of selected checkpoint provenance."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import torch

from .audit import require, verify_procedure, verify_selection_v2, source_closure
from .operations import ROOT, EXT, evidence
from .study_v2 import selection
from .tasks import read, sha, write


def binding(path):
    return {'path':str(Path(path).relative_to(ROOT)),'sha256':sha(path)}


def verify_reconciliation(report):
    require(report['passed'] and report['new_training']==0,'Invalid attribution repair')
    for b in [report['original_procedure'],report['corrected_procedure']]:
        require(sha(ROOT/b['path'])==b['sha256'],'Procedure binding changed')
    old=read(ROOT/report['original_procedure']['path'])
    new=read(ROOT/report['corrected_procedure']['path'])
    verify_procedure(old); verify_procedure(new)
    require({k:v for k,v in old.items() if k!='studies'}==
            {k:v for k,v in new.items() if k!='studies'},'Procedure outcomes changed')
    for before_path,after_path in zip(old['studies'],new['studies']):
        before,after=read(before_path),read(after_path)
        require(before['schema']==2 and after['schema']==3,'Wrong attribution versions')
        keys=set(before)-{'schema','selection_rule','selected'}
        require(all(before[k]==after[k] for k in keys),'Training evidence altered')
        for method,key in [('bgpbt','population_results'),('baseline','baseline_results')]:
            a,b=before['selected'][method],after['selected'][method]
            require(a['cost']==b['cost'],'Attribution repair changed the measured objective')
            rows=[read(Path(d)/'result.json') for d in after[key]]
            require(selection(rows)==b,'Selected result is not a trained minimum')
            x=torch.jit.load(str(Path(a['task'])/'actor.pt')).state_dict()
            y=torch.jit.load(str(Path(b['task'])/'actor.pt')).state_dict()
            require(x.keys()==y.keys() and all(torch.equal(x[k],y[k]) for k in x),
                    'Attribution repair changed selected actor weights')
    return True


def run(out):
    subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--basetemp='+str(out/'pytest'),'--junitxml='+str(out/'tests.xml'),
        str(EXT/'tests/test_repair.py'),'-k','not actual_candidate'],check=True,timeout=180)
    suites=list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
    require(sum(int(s.get('tests',0)) for s in suites)==4 and
            not any(int(s.get('skipped',0)) for s in suites),'Focused repair roster incomplete')
    original=evidence('procedure-check')
    require(source_closure(original.parent)['passed'],'Original procedure did not finish')
    raw=read(original); verify_procedure(raw); corrected=deepcopy(raw); paths=[]; changes=[]
    for path in raw['studies']:
        study=read(path); repaired=deepcopy(study)
        repaired.update(schema=3,selection_rule='best_evaluated_trained_checkpoint')
        for method,key in [('bgpbt','population_results'),('baseline','baseline_results')]:
            rows=[read(Path(d)/'result.json') for d in study[key]]
            repaired['selected'][method]=selection(rows)
        verify_selection_v2(repaired)
        target=out/f"seed-{study['seed']}-selection.json"; write(target,repaired); paths.append(str(target))
        changes.append({'seed':study['seed'],'original':binding(Path(path)),
                        'corrected':binding(target),'before':study['selected'],'after':repaired['selected']})
    corrected['studies']=paths; target=out/'procedure-corrected.json'; write(target,corrected)
    report={'passed':True,'new_training':0,'tests':4,'original_procedure':binding(original),
            'corrected_procedure':binding(target),'changes':changes}
    verify_reconciliation(report)
    bad=read(paths[0]); bad['selected']['bgpbt']=read(raw['studies'][0])['selected']['bgpbt']
    try: verify_selection_v2(bad)
    except ValueError: report['negative_control']='untrained_copy_as_trained_selection_rejected'
    else: raise ValueError('Untrained copy was accepted as a trained winner')
    write(out/'selection-reconciliation-result.json',report)
    print({'passed':True,'new_training':0,'corrected_procedure':str(target)},flush=True)
