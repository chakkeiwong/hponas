"""Zero-training documentation from a completed, hash-bound study."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/'extensions/rl-lqr10'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-04'

def binding(p):return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def main():
    index=json.loads((EXT/'results-index.json').read_text());b=index['study'];path=ROOT/b['path']
    if binding(path)!=b:raise ValueError('Study evidence changed')
    r=json.loads(path.read_text());o=r['oracle'];out=BASE/'documentation'
    if out.exists():raise ValueError('Documentation allocation already exists')
    out.mkdir()
    lines=['# Ten-state, thirty-step results','',
        'RL-LQR-04: three paired joint SAC architecture/rate tuning procedures.',
        'The following are held-out sample estimates conditional on frozen policies, not exact neural-policy costs.','',
        f"Analytical optimum: **{o['optimal_cost']:.12f}**. Zero action: **{o['zero_action_cost']:.12f}**.",
        f"Certified maximum oracle action: {o['max_oracle_action_bound']:.12f}, below the bound 1.",'',
        '| Search seed | BG-PBT cost | BG-PBT gap (normal 95% interval) | Static cost | Paired difference |',
        '| --- | ---: | --- | ---: | ---: |']
    tex=[r'\begin{center}\begin{tabular}{rrrrr}\toprule',
        r'Seed & BG-PBT cost & Gap & Static cost & Difference\\\midrule']
    for test in r['tests']:
        a=test['methods']['bgpbt'];s=test['methods']['baseline'];lo,hi=a['gap_normal95']
        lines.append(f"| {test['seed']} | {a['cost']:.6f} | {a['gap']:.6f} [{lo:.6f}, {hi:.6f}] | {s['cost']:.6f} | {test['paired_test_difference']:+.6f} |")
        tex.append(f"{test['seed']} & {a['cost']:.6f} & {a['gap']:.6f} & {s['cost']:.6f} & {test['paired_test_difference']:+.6f}"+r'\\')
    tex+=[r'\bottomrule\end{tabular}\end{center}']
    lines+=['','Negative paired differences favor BG-PBT. Intervals are approximate test-path uncertainty; they do not include training-seed uncertainty.',
        '',f"Mean paired difference: {r['mean_paired_test_difference']:+.6f}; sign-randomization diagnostic p={r['sign_randomization_diagnostic_p']:.2f}. Three pairs do not establish general superiority.",
        '', '## Selected training lineages','']
    tex += [f"Mean paired difference is {r['mean_paired_test_difference']:+.6f}; the paired sign-randomization diagnostic is {r['sign_randomization_diagnostic_p']:.2f}. "
            'Three optimizer seeds do not establish general superiority. All scores use the separate test paths after validation selection.']
    for test in r['tests']:
        a=test['methods']['bgpbt'];c=a['config'];lo,hi=a['gap_normal95']
        recovered=100*(o['zero_action_cost']-a['cost'])/(o['zero_action_cost']-o['optimal_cost'])
        lines += [f"- Seed {test['seed']}: actor {c['actor_hiddens']}; critic {c['critic_hiddens']}; actor rate {c['actor_lr']:.9g}; critic rate {c['critic_lr']:.9g}. Recovers {recovered:.2f}% of the available improvement over no action."]
        tex += [f"\\paragraph{{Seed {test['seed']}.}} Actor widths {c['actor_hiddens']}, critic widths {c['critic_hiddens']}, "
            f"actor rate {c['actor_lr']:.9f}, critic rate {c['critic_lr']:.9f}. The excess-cost interval is [{lo:.6f}, {hi:.6f}]. "
            f"The policy recovers {recovered:.2f}\\% of the available improvement over zero action."]
    lines+=['','## Limits and work','',*['- '+x for x in r['limitations']],
        '',f"Study work: {r['work']['transitions']:,} transitions, {r['work']['sac_updates']:,} SAC updates, {r['work']['distillation_updates']:,} distillation updates.",
        '', 'The run is complete at the declared budget. Reaching a small gap does not establish stable convergence, zero error or global HPO/NAS optimality.',
        '', 'Source and data: '+str(path.relative_to(ROOT)), '']
    tex += ['The measured gaps remain nonzero. This experiment demonstrates bounded learning outcomes, '
        'not stable convergence to the analytical optimum or global optimality of architecture and rates. '
        'Fourteen engineering checks pass before allocation. All outputs and unfavorable comparisons are retained.']
    (EXT/'RESULTS.md').write_text('\n'.join(lines))
    (out/'lqr10-measured-results.tex').write_text('\n'.join(tex)+'\n')
    previous=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03/20261027T125923Z-hardware-documentation-a1e74359'
    older=ROOT/'docs/program/evidence/2026-10-26/parallel-publication-refresh-05/build-01'
    wrapper=(previous/'main-lqr5-bgpbt.tex').read_text().replace(r'\input{27-lqr5-bgpbt}',r'\input{28-lqr10-h30}'+'\n'+r'\input{27-lqr5-bgpbt}',1)
    wrapper=wrapper.replace('five-state SAC BG-PBT companion','ten-state horizon-thirty experiment')
    (out/'main-lqr10-h30.tex').write_text(wrapper)
    env={k:os.environ[k] for k in ('HOME','USER','LOGNAME','LANG','PATH') if k in os.environ}
    env['TEXINPUTS']=os.pathsep.join(map(str,[out,EXT/'docs',previous,ROOT/'extensions/rl-lqr5-bgpbt/docs',ROOT/'extensions/rl-lqr/docs',older,ROOT/'hpo-survey']))+os.pathsep
    env['BIBINPUTS']=str(ROOT/'hpo-survey')+os.pathsep;env['BSTINPUTS']=env['BIBINPUTS']
    latex=['/usr/bin/pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-output-directory='+str(out),str(out/'main-lqr10-h30.tex')]
    commands=[latex,['/usr/bin/bibtex','main-lqr10-h30'],latex,latex,latex,
              ['/usr/bin/pdftotext','-layout',str(out/'main-lqr10-h30.pdf'),str(out/'manual.txt')]]
    for i,cmd in enumerate(commands):
        with (out/f'build-{i}.log').open('x') as log:subprocess.run(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    rendered=''.join((out/'manual.txt').read_text().split())
    for expected in ['Ten-state, thirty-step joint SAC tuning','7.8716918755290335','10301','10302','10303','466,944']:
        if ''.join(expected.split()) not in rendered:raise ValueError('Required rendered statement missing: '+expected)
    log=(out/'main-lqr10-h30.log').read_text()
    if any(s in log for s in ['There were undefined references','There were undefined citations','Rerun to get cross-references right','LaTeX Error:']):raise ValueError('Unresolved manual references')
    report=dict(passed=True,new_training=0,study=b,inputs=[binding(Path(__file__)),binding(EXT/'docs/28-lqr10-h30.tex'),binding(previous/'main-lqr5-bgpbt.tex')],
        outputs=[binding(p) for p in [EXT/'RESULTS.md',out/'lqr10-measured-results.tex',out/'main-lqr10-h30.tex',out/'main-lqr10-h30.pdf',out/'manual.txt']])
    (out/'documentation-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
