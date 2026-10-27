"""Versioned manual build; no mutation of consumed predecessor documentation."""
import os, subprocess, sys
from common import *

def run(out):
    survey=ROOT/'hpo-survey'; manifest=read(BASE/'documentation-manifest.json')
    for item in manifest['inputs']: assert binding(ROOT/item['path'])==item
    # Source files stay at their reviewed paths. Only generated outputs go here.
    env=os.environ.copy(); env['BIBINPUTS']=str(survey)+':'; env['TEXINPUTS']=str(survey)+'//:'
    passes=[['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','-no-shell-escape','-recorder','-output-directory='+str(out),'main-app03.tex'],
            ['/usr/bin/bibtex','main-app03'],
            ['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','-no-shell-escape','-recorder','-output-directory='+str(out),'main-app03.tex'],
            ['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','-no-shell-escape','-recorder','-output-directory='+str(out),'main-app03.tex']]
    for i,args in enumerate(passes):
        r=subprocess.run(args,cwd=out if i==1 else survey,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=65)
        (out/f'build-{i+1}.log').write_text(r.stdout)
        if r.returncode: raise RuntimeError('Manual build failed at pass '+str(i+1))
    subprocess.run(['/usr/bin/pdftotext','-layout',str(out/'main-app03.pdf'),str(out/'main-app03.txt')],check=True,timeout=20)
    pdf=(out/'main-app03.pdf').read_bytes(); assert pdf.startswith(b'%PDF') and len(pdf)>100000
    content=(out/'main-app03.txt').read_text(); log=(out/'main-app03.log').read_text()
    required=['Application repairs and fresh evidence','0.5753800514','72 fits','291','27 fits','0.0018289500','identification','655,360']
    assert all(x in content for x in required)
    assert 'undefined references' not in log and 'Citation ' not in log and 'LaTeX Error' not in log
    declared={str((ROOT/x['path']).resolve()) for x in manifest['inputs']}; local=set()
    for line in (out/'main-app03.fls').read_text().splitlines():
        if not line.startswith('INPUT '): continue
        f=Path(line[6:]); f=f if f.is_absolute() else survey/f; f=f.resolve()
        if f.is_relative_to(ROOT) and not f.is_relative_to(out):
            assert str(f) in declared, 'Unbound local TeX input: '+str(f); local.add(str(f.relative_to(ROOT)))
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'documentation_only','pdf':binding(out/'main-app03.pdf'),'pages':content.count('\f'),
          'source_inputs_seen':sorted(local),'build_passes':4,'required_outcome_markers':required,'predecessor_unchanged':True,
          'scope':'Versioned current companion manual; scientific audit and terminal master closure remain separate.'})
if __name__=='__main__':run(Path(sys.argv[1]))
