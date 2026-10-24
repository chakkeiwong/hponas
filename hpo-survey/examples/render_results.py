"""Generate LaTeX tables and a standalone figure only from retained outputs."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'docs/program/evidence/2026-10-24/doc-01'


def load(name):
    eligible=[p.parent for p in BASE.glob('*-'+name+'-*/receipt.json') if json.loads(p.read_text())['passed']]
    assert len(eligible)==1
    path=eligible[0]/'results/summary.json'
    return path,json.loads(path.read_text())


def main():
    sources=[];data={}
    for name in ('response','equilibrium'):
        path,s=load(name);data[name]=s;sources.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        lines=[r'\begin{table}[htbp]',r'\centering\small',
               r'\begin{tabular}{rlrrrrr}',r'\toprule',
               r'Seed & Method & Tuning loss & Regret & Final loss & Unique & Seconds \\',
               r'\midrule']
        for row in s['rows']:
            fmt='.6f' if name=='response' else '.3g'
            lines.append(f"{row['replicate']} & {row['method'].upper() if row['method'] in ('gp','tpe') else row['method'].capitalize()} & {row['best_tuning']:{fmt}} & {row['regret']:.3g} & {row['final_mean']:{fmt}} & {row['unique']} & {row['seconds']:.2f} "+r'\\')
        lines += [r'\bottomrule',r'\end{tabular}',r'\caption{'+('Response NLL' if name=='response' else 'Neural equilibrium residual MSE')+r' results. Each search spends 12 proposals. Unique counts include no free replacement for duplicates. Seconds measure the persisted search and protected final evaluation; full-grid reference time is separate.}',r'\end{table}']
        (ROOT/f'hpo-survey/sections/generated-{name}-results.tex').write_text('\n'.join(lines)+'\n')
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(9,3.4),layout='constrained')
    methods=('random','sobol','gp','tpe');colors=('#4477AA','#228833','#CC6677','#AA3377')
    for j,(method,color) in enumerate(zip(methods,colors)):
        rows=[r for r in data['equilibrium']['rows'] if r['method']==method]
        axes[0].plot([1,2,3],[r['regret'] for r in rows],'o-',label=method,color=color)
        axes[1].bar(np.arange(3)+(j-1.5)*.19,[r['final_mean'] for r in rows],width=.18,label=method,color=color)
    axes[0].set(xlabel='Dataset seed',ylabel='Finite tuning regret',xticks=[1,2,3],xticklabels=['101','202','303'])
    axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0));axes[0].legend(fontsize=8)
    axes[1].set(xlabel='Dataset seed',ylabel='Protected final residual MSE',yscale='log',xticks=[0,1,2],xticklabels=['101','202','303'])
    figures=ROOT/'hpo-survey/figures';figures.mkdir(exist_ok=True);fig.savefig(figures/'doc01-results.pdf');fig.savefig(figures/'doc01-results.png',dpi=160);plt.close(fig)
    (Path(sys.argv[1])/'generation.json').write_text(json.dumps({'sources':sources,'outputs':['hpo-survey/sections/generated-response-results.tex','hpo-survey/sections/generated-equilibrium-results.tex','hpo-survey/figures/doc01-results.pdf']},indent=2)+'\n')
    print(json.dumps({'passed':True,'sources':sources,'generated':'two complete tables and standalone NAS figure'}))


if __name__=='__main__':main()
