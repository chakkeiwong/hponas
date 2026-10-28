"""Zero-training publication and supplementary result checks for RL-LQR-05."""
from pathlib import Path
import hashlib
import json
import math
import os
import subprocess
ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/'extensions/rl-lqr-multi'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-05'
def binding(p):return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def load(p):return json.loads(p.read_text())
def main():
    index=load(EXT/'results-index.json');b=index['study'];path=ROOT/b['path']
    if binding(path)!=b:raise ValueError('Study evidence changed')
    r=load(path);out=BASE/'documentation'
    if out.exists():raise ValueError('Documentation allocation already exists')
    out.mkdir()
    freeze=load(path.parent/'all-selections-frozen.json')
    if freeze['selection_bindings']!=r['selection_bindings'] or freeze['test_seed']!=1050002 or freeze['test_paths']!=16384:
        raise ValueError('Global holdout freeze differs')
    lines=['# Ten-state multi-action tuning results','',
        'RL-LQR-05: action dimensions 2, 3, 4, 5; ten physical states; horizon thirty.',
        'Held-out cost estimates conditional on frozen policies. Analytical references are independently verified.',
        '', '| Actions | Exact optimum | Zero-action cost | Max oracle coordinate |',
        '| --- | ---: | ---: | ---: |']
    tex=[r'\begin{center}\begin{tabular}{rrrr}\toprule',r'Actions & Optimum & Zero action & Oracle bound\\\midrule']
    for m,o in r['oracles'].items():
        lines.append(f"| {m} | {o['optimal_cost']:.9f} | {o['zero_action_cost']:.9f} | {o['max_oracle_action_bound']:.9f} |")
        tex.append(f"{m} & {o['optimal_cost']:.6f} & {o['zero_action_cost']:.6f} & {o['max_oracle_action_bound']:.6f}"+r'\\')
    tex += [r'\bottomrule\end{tabular}\end{center}']
    lines += ['', '| Actions | Seed | BG-PBT cost | Gap [normal 95% interval] | Improvement recovered | Static cost | Default cost |',
              '| --- | --- | ---: | --- | ---: | ---: | ---: |']
    tex += [r'\begin{center}\begin{tabular}{rrrrrrr}\toprule',r'$m$ & Seed & BG-PBT & Gap & Recovered (\%) & Static & Default\\\midrule']
    for t in r['tests']:
        m=t['actions'];o=r['oracles'][str(m)];a=t['methods']['bgpbt'];s=t['methods']['baseline'];d=t['methods']['default']
        lo,hi=a['gap_normal95'];fraction=(o['zero_action_cost']-a['cost'])/(o['zero_action_cost']-o['optimal_cost'])
        if abs(fraction-a['available_improvement_recovered'])>1e-12:raise ValueError('Improvement calculation differs')
        if abs(a['gap']/o['optimal_cost']-a['relative_optimality_gap'])>1e-12:raise ValueError('Relative gap differs')
        for comparator in ('baseline','default'):
            c=t['contrasts'][comparator];difference=a['cost']-t['methods'][comparator]['cost']
            if abs(difference-c['mean'])>1e-12:raise ValueError('Paired difference differs')
            expected=[c['mean']-1.959963984540054*c['standard_error'],c['mean']+1.959963984540054*c['standard_error']]
            if expected!=c['normal95']:raise ValueError('Paired interval differs')
        lines.append(f"| {m} | {t['seed']} | {a['cost']:.6f} | {a['gap']:.6f} [{lo:.6f}, {hi:.6f}] | {fraction:.2%} | {s['cost']:.6f} | {d['cost']:.6f} |")
        tex.append(f"{m} & {t['seed']} & {a['cost']:.6f} & {a['gap']:.6f} & {100*fraction:.2f} & {s['cost']:.6f} & {d['cost']:.6f}"+r'\\')
    tex += [r'\bottomrule\end{tabular}\end{center}']
    lines += ['', '## Aggregation across three optimizer seeds','',
              '| Actions | Mean BG-PBT | Mean static | Mean default | Mean recovered | BG-PBT wins vs static |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    summaries=[]
    for m in r['actions']:
        rows=[t for t in r['tests'] if t['actions']==m];means={method:sum(t['methods'][method]['cost'] for t in rows)/len(rows) for method in ('bgpbt','baseline','default')}
        recovered=sum(t['methods']['bgpbt']['available_improvement_recovered'] for t in rows)/len(rows)
        wins=sum(t['contrasts']['baseline']['mean']<0 for t in rows)
        lines.append(f"| {m} | {means['bgpbt']:.6f} | {means['baseline']:.6f} | {means['default']:.6f} | {recovered:.2%} | {wins}/3 |")
        summaries.append(dict(actions=m,mean_costs=means,mean_improvement_recovered=recovered,wins_vs_static=wins))
        tex.append(f"\\paragraph{{{m} actions.}} Mean BG-PBT cost {means['bgpbt']:.6f}, static {means['baseline']:.6f}, default {means['default']:.6f}; mean recovered improvement {100*recovered:.2f}\\%. BG-PBT wins {wins}/3 paired seed comparisons with static search.")
    lines += ['', 'Arithmetic means describe these three seeds only. A win count or small test-path interval does not establish general method superiority.',
        'Default uses a smaller total tuning budget; static search is the matched-work comparator.','', '## Selected lineages and paired comparisons','']
    for t in r['tests']:
        a=t['methods']['bgpbt'];c=a['config'];lo,hi=a['gap_normal95']
        lines += [f"- Actions {t['actions']}, seed {t['seed']}: actor {c['actor_hiddens']}; critics {c['critic_hiddens']}; actor LR {c['actor_lr']:.9g}; critic LR {c['critic_lr']:.9g}. Selected checkpoint: {a['selection_task']}."]
        tex += [f"\\paragraph{{Actions {t['actions']}, seed {t['seed']}.}} Actor widths {c['actor_hiddens']}, critic widths {c['critic_hiddens']}, actor rate {c['actor_lr']:.9g}, critic rate {c['critic_lr']:.9g}. Gap interval [{lo:.6f}, {hi:.6f}]."]
        for comparator in ('baseline','default'):
            contrast=t['contrasts'][comparator];lo,hi=contrast['normal95']
            lines += [f"  Paired BG-PBT minus {comparator}: {contrast['mean']:+.6f}, normal95 [{lo:+.6f}, {hi:+.6f}]."]
            tex += [f"Paired difference against {comparator}: {contrast['mean']:+.6f}, approximate interval [{lo:+.6f}, {hi:+.6f}]."]
    for frozen in r['selection_bindings']:
        p=ROOT/frozen['path']
        if binding(p)!=frozen:raise ValueError('Selection source changed')
        selection=load(p)
        for group in ('population_results','baseline_results'):
            for directory in selection[group]:
                task=load(Path(directory)/'result.json')['task']
                if task['actions']!=selection['actions']:raise ValueError('Cross-dimensional procedure task')
        for role in ('bgpbt','baseline'):
            work=selection['work'][role]
            if work['transitions']!=77824 or work['gradient_components']!=77568:raise ValueError('Per-procedure work differs')
    lines += ['', '## Work and scientific limits','',*['- '+x for x in r['limitations']],
              '',f"Actual training: {r['work']['transitions']:,} transitions, {r['work']['sac_updates']:,} SAC updates, {r['work']['distillation_updates']:,} distillation updates.",
              '', 'Cost gaps are nonzero at the declared budget. This is not a convergence certificate, a global architecture optimum, or proof of universal BG-PBT superiority.',
              '', 'Evidence: '+str(path.relative_to(ROOT)),'']
    tex += ['All outcomes, including worse comparisons, remain reported. These are fixed-budget results with nonzero regret, not convergence or global architecture optimality certificates. The selection rates describe evolving training lineages, not separately validated fresh static recipes.']
    (EXT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    (out/'lqr-multi-measured-results.tex').write_text('\n'.join(tex)+'\n')
    previous=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-04/documentation'
    bgpbt=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03/20261027T125923Z-hardware-documentation-a1e74359'
    older=ROOT/'docs/program/evidence/2026-10-26/parallel-publication-refresh-05/build-01'
    wrapper=(previous/'main-lqr10-h30.tex').read_text().replace(r'\input{28-lqr10-h30}',r'\input{29-lqr-multi-action}'+'\n'+r'\input{28-lqr10-h30}',1)
    wrapper=wrapper.replace('ten-state horizon-thirty experiment','multi-action ten-state experiment')
    (out/'main-lqr-multi.tex').write_text(wrapper)
    env={k:os.environ[k] for k in ('HOME','USER','LOGNAME','LANG','PATH') if k in os.environ}
    env['TEXINPUTS']=os.pathsep.join(map(str,[out,EXT/'docs',previous,ROOT/'extensions/rl-lqr10/docs',bgpbt,ROOT/'extensions/rl-lqr5-bgpbt/docs',ROOT/'extensions/rl-lqr/docs',older,ROOT/'hpo-survey']))+os.pathsep
    env['BIBINPUTS']=str(ROOT/'hpo-survey')+os.pathsep;env['BSTINPUTS']=env['BIBINPUTS']
    latex=['/usr/bin/pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-output-directory='+str(out),str(out/'main-lqr-multi.tex')]
    commands=[latex,['/usr/bin/bibtex','main-lqr-multi'],latex,latex,latex,
              ['/usr/bin/pdftotext','-layout',str(out/'main-lqr-multi.pdf'),str(out/'manual.txt')]]
    for i,cmd in enumerate(commands):
        with (out/f'build-{i}.log').open('x') as log:subprocess.run(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    rendered=''.join((out/'manual.txt').read_text().split())
    for expected in ['Multi-action joint SAC tuning','10501','10502','10503','1,867,776','463,104','3,072','7.281976','5.513248']:
        if ''.join(expected.split()) not in rendered:raise ValueError('Required rendered statement missing: '+expected)
    log=(out/'main-lqr-multi.log').read_text()
    if any(s in log for s in ['There were undefined references','There were undefined citations','Rerun to get cross-references right','LaTeX Error:']):raise ValueError('Unresolved manual references')
    report=dict(passed=True,new_training=0,study=b,summary=summaries,
        inputs=[binding(Path(__file__)),binding(EXT/'README.md'),binding(EXT/'docs/29-lqr-multi-action.tex'),binding(previous/'main-lqr10-h30.tex')],
        outputs=[binding(p) for p in [EXT/'RESULTS.md',out/'lqr-multi-measured-results.tex',out/'main-lqr-multi.tex',out/'main-lqr-multi.pdf',out/'manual.txt']])
    (out/'documentation-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
