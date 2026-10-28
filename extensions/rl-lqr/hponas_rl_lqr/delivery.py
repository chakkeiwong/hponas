"""Versioned documentation and independent completion checks; no training."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

from .audit import read, sha, require, verify_fit, verify_selection, verify_hardware, negative_controls

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT/'extensions/rl-lqr'
BASE = ROOT/'docs/program/evidence/2026-10-27/rl-lqr-01'
CORE = 'fb5a83647bd5d73aaff21e360bab73432c670c6b08038e52507749a7de99e320'
PREVIOUS_MANUAL = ROOT/'docs/program/evidence/2026-10-26/parallel-publication-refresh-05/build-01'


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def bind(path):
    return {'path':str(Path(path).relative_to(ROOT)), 'sha256':sha(path)}


def index():
    records = read(EXT/'results-index.json')
    for role, ref in records.items():
        require(sha(ROOT/ref['path']) == ref['sha256'], 'Evidence index changed: '+role)
    return {role:(ROOT/ref['path']).parent for role,ref in records.items()}


def source_bindings(directory):
    manifest = read(directory/'manifest.json')
    for ref in [manifest['runner'], *manifest['inputs']]:
        require(sha(directory/'inputs'/ref['path']) == ref['sha256'], 'Consumed input differs: '+ref['path'])
    receipt = read(directory/'receipt.json')
    require(receipt['core_source'] == receipt['end_core_source'] == CORE, 'Core evidence identity differs')
    require(receipt['inputs_unchanged'] and not receipt['remaining_children'] and receipt['stop_reason'] is None,
            'Operation did not close cleanly')
    require(sha(ROOT/receipt['log']['path']) == receipt['log']['sha256'], 'Execution log differs')
    return {'directory':str(directory.relative_to(ROOT)), 'inputs_verified':len(manifest['inputs'])+1,
            'passed':receipt['passed']}


def audit(out):
    out = Path(out)
    from tools.source_identity import source_digest
    require(source_digest(ROOT) == CORE, 'Qualified core source changed')
    refs = index()
    operations = [source_bindings(p) for p in dict.fromkeys(refs.values())]
    allowed_failures = {refs['joint'].name, refs['hardware_predecessor'].name}
    require(all(x['passed'] for x in operations if Path(x['directory']).name not in allowed_failures),
            'A prerequisite failed')
    replay = read(refs['joint_replay']/'joint-replay-result.json')
    require(replay['passed'] and replay['new_transitions'] == replay['new_dispatches'] == 0 and
            not replay['differences'] and replay['original_evidence_unchanged'], 'Completed replay failed')
    joint = refs['joint']
    paths = sorted(joint.glob('fits/*/fit-result.json'))
    checked = {p.parent.name:verify_fit(p.parent) for p in paths}
    raw = {p.parent.name:read(p) for p in paths}
    snapshot = read(joint/'study/rl-lqr-joint_checkpoint.json')
    selection = verify_selection(snapshot, raw, read(joint/'study/selection-freeze.json'))
    # Actual CPU training intervals must overlap on disjoint worker CPUs.
    cpu_pairs = []
    for tid in snapshot['trials']:
        pair = [raw[tid+'_tuning_'+str(i)] for i in (0,1)]
        overlap = min(r['training_finished_epoch'] for r in pair)-max(r['training_started_epoch'] for r in pair)
        require(overlap > 0 and pair[0]['pid'] != pair[1]['pid'] and
                not set(pair[0]['cpu_affinity']) & set(pair[1]['cpu_affinity']), 'No distinct concurrent CPU training')
        cpu_pairs.append({'trial':tid, 'training_overlap_seconds':overlap})
    hardware = verify_hardware(read(refs['hardware']/'hardware-result.json'))
    for p in sorted(refs['hardware'].glob('gpu-*/fit-result.json')):
        checked['hardware/'+p.parent.name] = verify_fit(p.parent)
    for p in sorted(refs['hardware_predecessor'].glob('gpu-*/fit-result.json')):
        checked['hardware_predecessor/'+p.parent.name] = verify_fit(p.parent)
    for name in ('initial','resumed'):
        checked['learner/'+name] = verify_fit(refs['learner']/name)
    learner = read(refs['learner']/'learner-result.json')
    identities = read(refs['learner']/'initial/checkpoint/lqr-integrity.json')['identities']
    require(learner['resumed']['restore']['identities'] == identities, 'Restored learner state differs')
    require(learner['resumed']['replay_total_added'] == learner['total_transitions'] == 1024, 'Resume work differs')
    controls = negative_controls(joint, refs['hardware'])
    build_record = read(refs['build']/'build-result.json')
    for ref in build_record['outputs']:
        require(sha(ROOT/ref['path']) == ref['sha256'], 'Manual bytes differ')
    require(sum(r['transitions'] for r in checked.values()) == 76800, 'Overall transition allocation differs')
    # Retain every produced output identity, including checkpoint bytes and failed attempts.
    inventory = {str(p.relative_to(ROOT)):sha(p) for d in BASE.iterdir()
                 if d.is_dir() and d != out and d.name != 'predecessor'
                 for p in d.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write(out/'artifact-inventory.json', inventory)
    result = {'passed':True, 'core_source':CORE, 'operations':operations,
              'fits_reconstructed':len(checked), 'training_transitions':76800,
              'independent_scores':checked, 'selection':selection, 'cpu_pairs':cpu_pairs,
              'hardware':hardware, 'negative_controls':controls,
              'artifact_inventory':bind(out/'artifact-inventory.json'),
              'scientific_outcome':'Frozen selected configuration failed to beat zero action on either fresh training seed.',
              'claims':{'integration_verified':True, 'bounded_roster_enumerated':True,
                        'learned_optimum':False, 'global_hpo_nas_optimum':False,
                        'reliable_learning':False, 'bg_pbt_sac_transfer':False}}
    write(out/'audit-result.json', result)
    print(json.dumps({k:result[k] for k in ('passed','fits_reconstructed','training_transitions','scientific_outcome')}))


def build(out):
    out = Path(out)
    env = os.environ.copy()
    env['TEXINPUTS'] = os.pathsep.join(map(str,(EXT/'docs',PREVIOUS_MANUAL,ROOT/'hpo-survey')))+os.pathsep
    env['BIBINPUTS'] = str(ROOT/'hpo-survey')+os.pathsep
    env['BSTINPUTS'] = str(ROOT/'hpo-survey')+os.pathsep
    latex = ['/usr/bin/pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',
             '-output-directory='+str(out),str(EXT/'docs/main-rl-lqr.tex')]
    commands = [latex, ['/usr/bin/bibtex','main-rl-lqr'],latex,latex,latex,
                ['/usr/bin/pdftotext','-layout',str(out/'main-rl-lqr.pdf'),str(out/'manual.txt')]]
    for i, command in enumerate(commands):
        with (out/f'build-{i}.log').open('x') as log:
            subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    text = ''.join((out/'manual.txt').read_text().split())
    required = ['Known-answer control and joint SAC tuning','1.078527','8.157594',
                '76,800','BG-PBT','512','13.049656','3.265531']
    require(all(''.join(t.split()) in text for t in required), 'Required rendered outcome missing')
    log = (out/'main-rl-lqr.log').read_text()
    require(not any(x in log for x in ('There were undefined references','There were undefined citations',
                                      'Rerun to get cross-references right','LaTeX Error:')), 'Unresolved LaTeX output')
    result = {'passed':True, 'required_rendered_statements':required,
              'outputs':[bind(out/n) for n in ('main-rl-lqr.pdf','manual.txt')],
              'new_training':0, 'historical_chapters_unchanged':True}
    write(out/'build-result.json',result)


def master_audit(out):
    """Final master-stage candidate check, after separate extension audit."""
    from tools.source_identity import source_digest
    from tools.gap_trace import validate
    from tools.program_continuation import continuation
    program = read(ROOT/'docs/program/program.json')
    stages = {s['id']:s for s in program['continuation']['steps']}
    require(stages['RL-LQR-01/AUDIT']['state'] == 'complete', 'Extension audit incomplete')
    require(source_digest(ROOT) == CORE, 'Core source changed')
    evidence = {e['id']:e for e in program['evidence']}
    for ref in stages['RL-LQR-01/AUDIT']['evidence_refs']:
        e = evidence[ref]
        require(sha(ROOT/e['path']) == e['sha256'], 'Audit evidence differs')
    accepted = read(ROOT/'docs/program/evidence/2026-10-26/parallel-qualification-run-04/accepted-package.json')
    require(accepted['source_digest'] == CORE and len(accepted['campaigns']) == 17 and len(accepted['gates']) == 5,
            'Original qualification binding differs')
    candidate = deepcopy(program)
    for step in candidate['continuation']['steps']:
        if step['id'] == 'GAP-01/FINAL-AUDIT':
            step['state'] = 'complete'
        require(step['state'] == 'complete', 'Unfinished stage: '+step['id'])
    for work in candidate['work_items']:
        if work['id'] == 'GAP-01':
            work['state'] = 'complete'
        require(work['state'] == 'complete', 'Unfinished work: '+work['id'])
    candidate['active_work_item'] = None
    validate(read(ROOT/'docs/program/gap_closure.json'), candidate, ROOT, final=True)
    status = continuation(candidate)
    require(status['master_complete'], 'Candidate master remains incomplete')
    # Counterexample: reopening an extension obligation must prevent completion.
    broken = deepcopy(candidate)
    next(s for s in broken['continuation']['steps'] if s['id']=='RL-LQR-01/LEARNER')['state']='planned'
    try:
        false_status = continuation(broken)
    except ValueError as exc:
        require('predecessor is incomplete' in str(exc), 'Unexpected counterexample failure')
    else:
        require(not false_status['master_complete'], 'False-completion counterexample accepted')
    result = {'passed':True, 'core_source':CORE, 'work_items':len(candidate['work_items']),
              'stages':len(candidate['continuation']['steps']), 'requirements':len(candidate['requirements']),
              'original_gap_trace_valid':True, 'unfinished_extension_refused':True,
              'candidate_master_complete':True, 'new_training':0,
              'scope':'Finite local master plus audited LQR integration; reliable SAC learning remains unestablished.'}
    write(Path(out)/'master-audit-result.json',result)
    print(json.dumps(result,indent=2))
