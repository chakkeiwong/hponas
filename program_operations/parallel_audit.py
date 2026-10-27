#!/usr/bin/python3 -I
"""Fixed PAR-01 evidence reconstruction; never qualifies scientific campaigns."""
import copy
import hashlib
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from uuid import uuid4

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-26/parallel-01'
OPS={'resources','executors','study','population','adapter','methods','ray','streaming','audit-controls','hardware','build'}
METHODS={'random','sobol','tpe','gp','cma','robust','trust','cost','asha','pasha','priorband','dehb',
         'finite-prior','categorical-priorband','pibo','warm','ranked-warm','rgpe','caller-adapter',
         'vector-random','vector-qlognehvi','vector-chebyshev','vector-nsgaii','pbt','pb2','bg'}

def bind(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def verify(binding):
    path=ROOT/binding['path']
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT):raise ValueError('Evidence path escapes source')
    if bind(path)!=binding:raise ValueError('Evidence bytes differ: '+binding['path'])
    return path

def read(binding):return json.loads(verify(binding).read_text())

def validate(manifest,digest):
    if set(manifest['operations'])!=OPS:raise ValueError('Incomplete operation roster')
    tests={};totals={};checks=[]
    for name,binding in manifest['operations'].items():
        receipt=read(binding);directory=verify(binding).parent
        if receipt.get('passed') is not True or receipt.get('scientific_acceptance') is not False:
            raise ValueError('Operation did not pass bounded development checks')
        if name!='hardware' and (receipt.get('source_digest')!=digest or receipt.get('end_source_digest')!=digest):
            raise ValueError('Operation source is stale')
        operation_manifest=json.loads((directory/'manifest.json').read_text())
        if hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()!=receipt['manifest']['sha256']:
            raise ValueError('Immutable operation manifest differs')
        runner=operation_manifest['runner']
        if bind(ROOT/runner['path'])!=runner:
            archived=read_runner=ROOT/manifest['runner_archives'][runner['sha256']]['path']
            verify(manifest['runner_archives'][runner['sha256']])
            if hashlib.sha256(archived.read_bytes()).hexdigest()!=runner['sha256']:
                raise ValueError('Executed runner version unavailable')
        for item in operation_manifest['inputs']:verify(item)
        if name=='hardware':
            if not receipt['inputs_unchanged'] or receipt['remaining_children'] or receipt['returncode']:
                raise ValueError('Hardware execution/cleanup failed')
            verify(receipt['log'])
            timing=json.loads((directory/'gpu-timing.json').read_text())
            if len({r['metadata']['physical_ids'][0] for r in timing['records']['2']})!=2:
                raise ValueError('Hardware did not use two distinct devices')
            gpu_methods=json.loads((directory/'gpu-methods.json').read_text())
            if len(gpu_methods)!=32 or any(not row['cuda_objective'] for row in gpu_methods):
                raise ValueError('GPU scalar family coverage is incomplete')
        else:
            for item in receipt['checks']:
                if item['returncode'] or item['stop_reason'] or item['remaining_children']:raise ValueError('Operation execution/cleanup failed')
                verify(item['log'])
        if name!='build':
            tree=ET.parse(directory/'tests.xml');cases=tree.findall('.//testcase')
            if not cases or any(c.find('failure') is not None or c.find('error') is not None or c.find('skipped') is not None for c in cases):
                raise ValueError('Test roster is empty, failed or skipped')
            tests[name]=[c.attrib.get('name','') for c in cases];totals[name]=len(cases)
        checks.append({'name':name,'passed':True,'receipt':binding})
    for token in ('replacement_survives','coordinator_death','concurrent_resource_admission','partial_parallel_adapter_commit','stale_parallel_commit'):
        if not any(token in case for cases in tests.values() for case in cases):raise ValueError('Required adverse control omitted: '+token)
    matrix=read(manifest['capability_matrix'])
    if len(matrix['methods'])!=len(METHODS) or {row['method'] for row in matrix['methods']}!=METHODS:
        raise ValueError('Incomplete method matrix')
    for row in matrix['methods']:
        if not row['cpu_evidence'] or not row['gpu_evidence']:raise ValueError('Missing execution route')
        for key in ('cpu_evidence','gpu_evidence'):
            for op,token in row[key]:
                if not any(token in case for case in tests[op]):raise ValueError('Method evidence omitted: '+row['method'])
    return {'checks':checks,'test_counts':totals,'total_tests':sum(totals.values()),'method_rows':len(matrix['methods'])}

def main():
    if sys.argv[1:]:raise ValueError('No arguments accepted')
    signal.alarm(300)
    started=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=json.loads((BASE/'audit-manifest.json').read_text())
    verify(manifest['runner'])
    if manifest['runner']!=bind(Path(__file__)):raise ValueError('Unreviewed audit runner')
    p=json.loads((ROOT/'docs/program/program.json').read_text());steps={s['id']:s for s in p['continuation']['steps']}
    if p['active_work_item']!='PAR-01' or steps['PAR-01/AUDIT']['state']!='in_progress':raise ValueError('Audit stage inactive')
    if any(steps[s]['state']!='complete' for s in steps['PAR-01/AUDIT']['dependencies']):raise ValueError('Audit dependency incomplete')
    spec=importlib.util.spec_from_file_location('source',ROOT/'tools/source_identity.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    digest=module.source_digest(ROOT)
    if digest!=manifest['source_digest']:raise ValueError('Audit source changed')
    result=validate(manifest,digest)
    controls=[]
    for damage in ('missing_operation','stale_source','missing_method','changed_receipt'):
        bad=copy.deepcopy(manifest);bad_digest=digest
        if damage=='missing_operation':bad['operations'].pop('hardware')
        elif damage=='stale_source':bad_digest='0'*64
        elif damage=='missing_method':bad['capability_matrix']['sha256']='0'*64
        else:bad['operations']['methods']['sha256']='0'*64
        try:validate(bad,bad_digest)
        except ValueError:controls.append({'damage':damage,'rejected':True})
        else:raise ValueError('False evidence accepted: '+damage)
    for b in manifest['documents']:verify(b)
    build=verify(manifest['operations']['build']).parent
    text=subprocess.run(['/usr/bin/pdftotext',str(build/'main-app03.pdf'),'-'],capture_output=True,text=True,check=True,timeout=30).stdout
    for token in ('Parallel CPU and GPU execution','ResourceSpec','ResourceExecutor','PAR-QUAL-01','Sequential','CPU-portable'):
        if token not in text:raise ValueError('Manual omits required content: '+token)
    if module.source_digest(ROOT)!=digest:raise ValueError('Source changed during audit')
    out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-audit-'+uuid4().hex[:8]);out.mkdir()
    result.update(kind='parallel_extension_development_audit_v1',passed=True,source_digest=digest,
        manifest=bind(BASE/'audit-manifest.json'),negative_controls=controls,seconds=time.monotonic()-started,
        scientific_acceptance=False,qualification_remaining='PAR-QUAL-01 then GAP-01/FINAL-AUDIT',pdf=bind(build/'main-app03.pdf'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+chr(10))
    print(json.dumps({'passed':True,'directory':str(out.relative_to(ROOT)),'tests':result['total_tests']}))

if __name__=='__main__':main()
