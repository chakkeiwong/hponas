"""Fixed offline SCI-03 package build/install. Retained dependencies are read-only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path('/home/ubuntu/workspace/hponas')
PACKAGE=ROOT/'extensions/scientific-checks'
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'
UV=ROOT/'.hponas-runtime/package-tools/bin/uv'
RUNTIME=ROOT/'.hponas-runtime/installation/py313'

def binding(f):return {'path':str(f.relative_to(ROOT)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')

def run(out):
    env=os.environ.copy();env.pop('PYTHONPATH',None);env['UV_CACHE_DIR']=str(out/'cache');env['UV_NO_CACHE']='1'
    steps=[]
    with tempfile.TemporaryDirectory(prefix='hponas-sci03-installed-',dir='/tmp') as temp:
        outside=Path(temp)
        def call(label,args,success=True):
            cp=subprocess.run(list(map(str,args)),cwd=outside,env=env,capture_output=True,text=True,timeout=60)
            (out/(label+'.log')).write_text(cp.stdout);(out/(label+'.stderr')).write_text(cp.stderr)
            steps.append({'label':label,'args':list(map(str,args)),'returncode':cp.returncode})
            dump(out/'steps.json',steps)
            if success and cp.returncode:raise RuntimeError(label+': '+cp.stderr[-2000:])
            if not success and cp.returncode==0:raise AssertionError(label+' unexpectedly accepted')
            return cp
        source=out/'source';shutil.copytree(PACKAGE,source,ignore=shutil.ignore_patterns('__pycache__'))
        call('build-venv',[UV,'venv','--offline','--python',RUNTIME/'bin/python',out/'build-environment'])
        site,=(out/'build-environment/lib').glob('python*/site-packages')
        spec=importlib.util.spec_from_file_location('retained_installer',ROOT/'program_operations/verify_gap_installation.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        prerequisites=helper.stage_build_prerequisites(ROOT/'.hponas-runtime/build-prerequisites',site)
        call('build',[UV,'build','--offline','--no-build-isolation','--python',out/'build-environment/bin/python','--wheel','--out-dir',out/'wheel',source])
        wheel,=(out/'wheel').glob('*.whl')
        call('install-venv',[UV,'venv','--offline','--python',RUNTIME/'bin/python',out/'installed'])
        site,=(out/'installed/lib').glob('python*/site-packages')
        retained,=(RUNTIME/'lib').glob('python*/site-packages')
        dependencies=[]
        # Read-only dependency links avoid duplicating ~65 MiB. No hponas core,
        # research directory, sibling package or system site-packages is exposed.
        for name in ['numpy','numpy.libs','numpy-2.5.3.dist-info','mpmath','mpmath-1.3.0.dist-info']:
            folder=retained/name
            if not folder.is_dir():raise ValueError('Missing pinned dependency '+name)
            if name.endswith('.dist-info'):
                shutil.copytree(folder,site/name)
            else:
                (site/name).symlink_to(folder,target_is_directory=True)
            dependencies.extend(binding(f) for f in sorted(folder.rglob('*')) if f.is_file() and '__pycache__' not in f.parts)
        py=out/'installed/bin/python'
        call('install',[UV,'pip','install','--offline','--python',py,wheel])
        call('dependency-check',[UV,'pip','check','--python',py])
        check="""import importlib,json,pathlib,sys,zipfile,importlib.metadata as m
root=pathlib.Path(sys.prefix).resolve(); package=importlib.import_module('hponas_scientific_checks')
assert pathlib.Path(package.__file__).resolve().is_relative_to(root)
assert importlib.util.find_spec('hponas') is None
with zipfile.ZipFile(sys.argv[1]) as z:
 files=[n for n in z.namelist() if n.endswith('.py')]
 for n in files:assert (pathlib.Path(package.__file__).parent.parent/n).read_bytes()==z.read(n)
print(json.dumps({'python':sys.version,'prefix':str(root),'package_origin':package.__file__,
 'cwd':str(pathlib.Path.cwd()),'files':files,'dependencies':{k:m.version(k) for k in ['numpy','mpmath']},
 'dependency_origins':{k:importlib.import_module(k).__file__ for k in ['numpy','mpmath']}}))
"""
        cp=call('origins',[py,'-I','-c',check,wheel]);origins=json.loads(cp.stdout)
        assert not Path(origins['cwd']).is_relative_to(ROOT)
        with zipfile.ZipFile(wheel) as z:
            files=[n for n in z.namelist() if n.startswith('hponas_scientific_checks/') and n.endswith('.py')]
            assert set(files)=={str(f.relative_to(source/'src')) for f in (source/'src').rglob('*.py')}
            assert all(z.read(n)==(source/'src'/n).read_bytes() for n in files)
        pi=outside/'pi.json';dump(pi,{'logits':[[0,0]],'borders':[0,.5,1],'incumbent_loss':.5})
        cp=call('cli-pi',[out/'installed/bin/hponas-scientific-checks','pi',pi]);assert json.loads(cp.stdout)['probabilities']==[.5]
        ref=outside/'reference.json';dump(ref,{'points':[[0,0],[1,2]]})
        cp=call('cli-reference',[py,'-I','-m','hponas_scientific_checks','reference',ref]);assert json.loads(cp.stdout)['inverse']==[[0.,0.],[1.,2.]]
        bad=outside/'bad.json';bad.write_text('{"points":[NaN,0]}')
        call('cli-nonfinite',[py,'-I','-m','hponas_scientific_checks','reference',bad],False)
        existing=outside/'existing.json';existing.write_text('retain')
        call('cli-overwrite',[py,'-I','-m','hponas_scientific_checks','pi',pi,'--output',existing],False)
        assert existing.read_text()=='retain'
        call('cli-unknown',[py,'-I','-m','hponas_scientific_checks','unknown',pi],False)
        bad.write_text(' '* (8*1024*1024+1))
        call('cli-oversize',[py,'-I','-m','hponas_scientific_checks','pi',bad],False)
        installed=[binding(f) for f in sorted((site/'hponas_scientific_checks').glob('*.py'))]
        dump(out/'dependency-bindings.json',dependencies)
        dump(out/'result.json',{'mechanics_passed':True,'distribution':'hponas-scientific-checks','version':'0.1.0',
            'wheel':binding(wheel),'python':str(py.relative_to(ROOT)),'origins':origins,'installed':installed,
            'source':[binding(f) for f in sorted(PACKAGE.rglob('*')) if f.is_file() and '__pycache__' not in f.parts],
            'dependencies':binding(out/'dependency-bindings.json'),'build_prerequisites':prerequisites,
            'cli_controls':4,'outside_checkout':True,'dependency_mode':'Explicit links to hashed retained NumPy/mpmath only; no system site packages or hponas core.',
            'qualification':'Installation and interface evidence only; saved-artifact verification is a required following stage.'})
        print(json.dumps({'wheel':str(wheel),'installed_python':str(py),'mechanics_passed':True}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
