"""Read-only reconstruction and successor manual build; no scientific training."""
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import torch

from .audit import independently_score, require, source_closure, verify_proposal, verify_selection, verify_task
from .operations import BASE, EXT, ROOT, evidence
from .tasks import read, sha, write

PREVIOUS=ROOT/'docs/program/evidence/2026-10-26/parallel-publication-refresh-05/build-01'


def diagnostic_nonanticipation(engineering):
    """Reproduce actual duplicate-row float32 rounding with retained actors."""
    from hponas_rl_lqr5.reference import LQR5Spec, enumerate_policy, paths
    results=[]
    candidates=sorted(engineering.glob('pytest/test_real_population*/study/generation-c*-rung1/actor.pt'))
    for path in candidates:
        actor=torch.jit.load(str(path)).eval(); state,noise=paths(); max_spread=0.
        for t in range(8):
            obs=np.column_stack((state,np.full(len(state),(8-t)/8))).astype(np.float32)
            with torch.no_grad(): actions=actor(torch.from_numpy(obs)).numpy()
            _,inv=np.unique(obs,axis=0,return_inverse=True)
            low=np.full(inv.max()+1,np.inf); high=np.full(inv.max()+1,-np.inf)
            np.minimum.at(low,inv,actions[:,0]); np.maximum.at(high,inv,actions[:,0])
            max_spread=max(max_spread,float(np.max(high-low)))
            state=state@LQR5Spec().A.T+actions.astype(float)@LQR5Spec().B.T+noise[:,t]
        def raw(x,t):
            obs=np.column_stack((x,np.full(len(x),(8-t)/8))).astype(np.float32)
            with torch.no_grad(): return actor(torch.from_numpy(obs)).numpy()
        try:
            report=enumerate_policy(raw); raw_pass=True; raw_error=report['identity_error']
        except ValueError:
            raw_pass=False; raw_error=None
        fixed=independently_score(path)
        results.append({'actor':str(path.relative_to(ROOT)),'max_duplicate_action_spread':max_spread,
                        'raw_identity_passed':raw_pass,'raw_identity_error':raw_error,
                        'canonical_cost':fixed['cost'],'canonical_identity_passed':True})
    return results


def build(out):
    cal_path=evidence('calibration'); search_path=evidence('search'); confirm_path=evidence('confirmation')
    eng_path=evidence('engineering')
    entries=[eng_path,cal_path,search_path,confirm_path]
    receipts=[source_closure(p.parent) for p in entries]
    require(all(r['passed'] for r in receipts),'CPU evidence prerequisite failed')
    cal,selection,confirm=map(read,(cal_path,search_path,confirm_path))
    verify_selection(selection)
    tasks=cal['tasks']+selection['population_results']+selection['baseline_results']+confirm['tasks']
    verified=[verify_task(d) for d in tasks]
    # Reconstruct raw selection and paired fresh confirmation independently.
    require(confirm['seeds']==[801,802,803] and confirm['budget']==cal['budget_per_member'],
            'Prospective confirmation contract differs')
    reconstructed={}
    for method in ('bgpbt','baseline'):
        rows=[read(Path(d)/'result.json') for d in confirm['tasks'] if Path(d).name.startswith(method+'-')]
        require([r['task']['seed'] for r in rows]==[801,802,803],'Confirmation seed mismatch')
        require(all(r['task']['kind']=='fresh' and not r['task'].get('input') and
                    r['task']['config']==selection['selected'][method]['config'] for r in rows),
                'Not fresh selected static training')
        reconstructed[method]=[r['score']['cost'] for r in rows]
        require(reconstructed[method]==confirm['costs'][method],'Reported confirmation differs')
    expected=[a-b for a,b in zip(reconstructed['bgpbt'],reconstructed['baseline'])]
    require(expected==confirm['paired_cost_differences_bgpbt_minus_baseline'],'Paired differences changed')
    # Audit negative controls run here even when hardware blocks the final audit.
    from copy import deepcopy
    negatives=[]
    for name,field in [('false_selection','selection'),('omitted_work','work'),('false_optimum','optimum')]:
        bad=deepcopy(selection)
        if field=='selection': bad['selected']['bgpbt']['cost']=0.
        elif field=='work': bad['work']['bgpbt']['transitions']-=1
        else: bad['global_optimum']=True
        try: verify_selection(bad)
        except ValueError: negatives.append(name)
        else: raise ValueError('False selection evidence accepted')
    bad=read(Path(tasks[0])/'result.json'); bad['score']['cost']=0.
    try: verify_task(tasks[0],bad)
    except ValueError: negatives.append('false_score')
    else: raise ValueError('False score accepted')
    # Verify all actual worker intervals for independent initial population pairs.
    initial=[read(Path(d)/'result.json') for d in selection['snapshots'][0]['members']]
    cpu_pairs=[]
    for i in (0,2):
        a,b=initial[i:i+2]
        overlap=min(a['training_finished_epoch'],b['training_finished_epoch'])-max(a['training_started_epoch'],b['training_started_epoch'])
        require(overlap>0 and a['pid']!=b['pid'] and not set(a['cpu_affinity']) & set(b['cpu_affinity']),
                'Actual population CPU training did not overlap')
        cpu_pairs.append({'members':[i,i+1],'overlap_seconds':overlap})
    index=read(EXT/'results-index.json'); hardware=None
    if 'hardware' in index:
        from .audit import verify_hardware
        hardware=read(evidence('hardware')); verify_hardware(hardware)
    hardware_status=('Two shared physical GPUs qualified with actual simultaneous SAC training and bounded owned memory.' if hardware else
                     'GPU qualification is incomplete. Shared devices are permitted; final audits remain open.')
    procedure_text=''
    if 'procedure-check' in index:
        from .audit import verify_procedure
        from .reconciliation import verify_reconciliation
        reconciliation=read(evidence('selection-reconciliation')); verify_reconciliation(reconciliation)
        procedure=read(ROOT/reconciliation['corrected_procedure']['path'])
        source_closure(evidence('procedure-check').parent)
        procedure_tasks=verify_procedure(procedure)
        verified.extend(verify_task(directory) for directory in procedure_tasks)
        rows_v2=['\\begin{center}\\begin{tabular}{rrrr}\\toprule',
                 'Search seed & BG-PBT variant & Static search & Difference\\\\\\midrule']
        for seed,path in zip(procedure['seeds'],procedure['studies']):
            study=read(path); a=study['selected']['bgpbt']['cost']; b=study['selected']['baseline']['cost']
            rows_v2.append(f'{seed} & {a:.6f} & {b:.6f} & {a-b:.6f}\\\\')
        rows_v2+=['\\bottomrule\\end{tabular}\\end{center}']
        procedure_text=('\\subsection{Selection review and repaired procedure evidence}\n'
            'The pilot winner was a random initial member, not the default network. '
            'Four architectures were distilled, but only two received SAC training. '
            'The first elimination ranked imitation loss before the proposed SAC rates could act. '
            'The trust radius also depended on member order. These limitations prompted a versioned repair. '
            'The original observations above remain unchanged.\\par\n'
            'The repaired controller updates its region once per population round, proposes architectures '
            'using an objective surrogate plus random exploration, trains all four proposed joint '
            'configurations before objective-based halving, and retains the best evaluated checkpoint. '
            'Each method receives 38912 transitions and 38656 component-gradient minibatches per search. '
            'Equal component counts do not mean equal FLOPs. These are three complete procedure replications, '
            'not repeated training of an identical static configuration.\\par\n'
            +'\n'.join(rows_v2)+f"\nMean paired difference is {procedure['mean_difference']:.6f}; "
            f"the two-sided paired sign-randomization diagnostic is {procedure['paired_sign_randomization_two_sided_p']:.2f}. "
            'Three paired search seeds do not establish general superiority. A baseline or initial winner '
            'is valid, and no global NAS optimum is certified. The replay distillation warm-start followed '
            'by SAC is a bounded BG-PBT adaptation, not a reproduction of annealed on-policy PPO transfer.\\par\n')
        attribution=('All three returned population policies used newly proposed architectures. '
            'The first two had a zero-update copy tied with their trained donor. A zero-training '
            'provenance repair selected the donor, verified identical actor tensors and cost, and '
            'retained the original reports. Final learning rates describe the saved training lineage, '
            'not a proven static recipe for retraining from scratch. ')
        procedure_text+=attribution
        for seed,path in zip(procedure['seeds'],procedure['studies']):
            study=read(path); c=study['selected']['bgpbt']['config']
            procedure_text+=(f" Seed {seed}: actor {c['actor_hiddens']}, critic {c['critic_hiddens']}, "
                f"actor rate {c['actor_lr']:.9f}, critic rate {c['critic_lr']:.9f}; "
                f"certified policy gap {study['selected']['bgpbt']['cost']-3.2540811593967556:.6f}. " )
    if hardware:
        receipt=read(evidence('hardware').parent/'receipt.json')
        peak=max(receipt['owned_gpu_peak_mib'].values())
        hardware_status+=(f" Initial GPU training overlapped by {hardware['training_overlap_seconds']:.3f} seconds; "
            f"compatible and changed-shape descendants overlapped by {hardware['transfer_training_overlap_seconds']:.3f} seconds. "
            f"Workers used at most {peak} MiB of observed process GPU memory. "
            'The earlier shared attempt exposed Ray auto-initialization during device lookup and '
            'was stopped by the host-memory guard before training. The assigned-device learner '
            'repair preserves upstream SAC methods and prevents worker Ray initialization. '
            'Eight adapter/device tests and the subsequent shared GPU run passed. '
            'No speedup claim is made on shared devices.')
    diagnostics=diagnostic_nonanticipation(eng_path.parent)
    cpu_audit={'passed':True,'tasks_reconstructed':len(verified),'verified_tasks':verified,
        'cpu_pairs':cpu_pairs,'negative_controls':negatives,'scoring_diagnostics':diagnostics,
        'hardware_complete':hardware is not None,'final_master_complete':False,
        'claims':{'cpu_bgpbt_companion_verified':True,'global_optimality':False,'bgpbt_superiority':False}}
    write(out/'cpu-audit-result.json',cpu_audit)
    rows=['\\begin{center}\\begin{tabular}{rrrr}\\toprule',
          'Seed & BG-PBT selection cost & Static baseline cost & Riccati gap\\\\\\midrule']
    for i,seed in enumerate(confirm['seeds']):
        a=confirm['costs']['bgpbt'][i]; b=confirm['costs']['baseline'][i]
        rows.append(f'{seed} & {a:.6f} & {b:.6f} & {a-3.2540811593967556:.6f}\\\\')
    rows+=['\\bottomrule\\end{tabular}\\end{center}']
    selected=selection['selected']['bgpbt']; config=selected['config']
    text=(f"Calibration finished with costs {cal['curves'][-1]['costs'][0]:.6f} and "
          f"{cal['curves'][-1]['costs'][1]:.6f}, at 1984 SAC updates per seed. The frozen budget "
          f"was {cal['budget_per_member']} transitions per member.\\par\n"
          f"The best population policy cost was {selected['cost']:.6f}; its Riccati gap was "
          f"{selected['cost']-3.2540811593967556:.6f}. The static baseline selected the same "
          f"configuration, with search cost {selection['selected']['baseline']['cost']:.6f}. "
          f"The actor hidden widths are {config['actor_hiddens']}; critic widths are {config['critic_hiddens']}. "
          f"Actor rate is {config['actor_lr']:.9f} and critic rate {config['critic_lr']:.9f}. "
          "The winning population member was an initial configuration retained through the run; "
          "new architecture students were tested but did not win this bounded search.\\par\n"
          + '\n'.join(rows)+f"\nThe fresh BG-PBT-selection mean cost is {confirm['means']['bgpbt']:.6f} "
          f"with sample standard deviation {confirm['standard_deviations']['bgpbt']:.6f}. "
          "Both methods select identical static configurations and receive identical fresh seeds "
          "and budgets. Their paired confirmation costs coincide; no BG-PBT superiority is established. "
          "All three policies' actual gaps are reported without a human acceptance threshold.\\par\n"
          +procedure_text+hardware_status+'\\par\n'
          f"The pilot passed thirteen engineering tests; the selection repair passed eighteen, "
          f"with four additional zero-training attribution checks. Independent CPU reconstruction checked {len(verified)} "
          "saved learner tasks, including exported actors and checkpoint identities; four "
          "false-score/selection/work/optimum controls were rejected. Earlier failed engineering "
          "attempts remain in the source-bound evidence. The final audit additionally requires "
          "the GPU evidence and current master reconciliation.\n")
    (out/'lqr5-measured-results.tex').write_text(text)
    # A successor wrapper preserves all consumed predecessor chapter bytes.
    wrapper=(ROOT/'extensions/rl-lqr/docs/main-rl-lqr.tex').read_text()
    wrapper=wrapper.replace('\\input{26-rl-lqr}','\\input{27-lqr5-bgpbt}\n\\input{26-rl-lqr}',1)
    wrapper=wrapper.replace('known-answer RLlib SAC extension','five-state SAC BG-PBT companion')
    (out/'main-lqr5-bgpbt.tex').write_text(wrapper)
    env=os.environ.copy(); env['TEXINPUTS']=os.pathsep.join(map(str,(out,EXT/'docs',ROOT/'extensions/rl-lqr/docs',PREVIOUS,ROOT/'hpo-survey')))+os.pathsep
    env['BIBINPUTS']=str(ROOT/'hpo-survey')+os.pathsep; env['BSTINPUTS']=str(ROOT/'hpo-survey')+os.pathsep
    latex=['/usr/bin/pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',
           '-output-directory='+str(out),str(out/'main-lqr5-bgpbt.tex')]
    commands=[latex,['/usr/bin/bibtex','main-lqr5-bgpbt'],latex,latex,latex,
              ['/usr/bin/pdftotext','-layout',str(out/'main-lqr5-bgpbt.pdf'),str(out/'manual.txt')]]
    for i,command in enumerate(commands):
        with (out/f'build-{i}.log').open('x') as log:
            subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    rendered=''.join((out/'manual.txt').read_text().split())
    required=['Five-state joint architecture and SAC tuning','3.2540811593967556',
              f"{selected['cost']:.6f}",f"{confirm['means']['bgpbt']:.6f}",'801','802','803','no BG-PBT superiority']
    if 'procedure-check' in index:
        required+=['9211','9212','9213','Selection review and repaired procedure evidence',
                   '3.264432','3.259412','3.271134','zero-training provenance repair']
    if hardware: required+=['shared physical GPUs','580 MiB','Ray auto-initialization']
    require(all(''.join(x.split()) in rendered for x in required),'Required manual outcome missing')
    log=(out/'main-lqr5-bgpbt.log').read_text()
    require(not any(s in log for s in ('There were undefined references','There were undefined citations',
                                     'Rerun to get cross-references right','LaTeX Error:')),'Unresolved manual reference')
    write(out/'documentation-result.json',{'passed':True,'hardware_complete':hardware is not None,
        'cpu_audit':{'path':str((out/'cpu-audit-result.json').relative_to(ROOT)),
                     'sha256':sha(out/'cpu-audit-result.json')},
        'outputs':[{'path':str((out/n).relative_to(ROOT)),'sha256':sha(out/n)}
                   for n in ('main-lqr5-bgpbt.pdf','manual.txt','lqr5-measured-results.tex')],
        'required_rendered_statements':required,'new_training':0})
