"""Bounded RLlib Torch SAC; select unregularized deterministic controller cost."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import pickle
import random
import time
from uuid import uuid4

import numpy as np
import torch
import ray
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.core import DEFAULT_MODULE_ID
from ray.rllib.core.columns import Columns
from ray.rllib.core.models.base import ENCODER_OUT
from ray.rllib.core.rl_module import RLModuleSpec

from hponas import (Config, EvaluationFold, EvaluationObjective,
                    RandomSearcher, SearchSpace, Knob, ResourceExecutor, ResourceSpec,
                    Study, StudyBudget, StudyDeclaration)
from .catalog import IndependentSACCatalog
from .environment import FiniteLQREnv
from .reference import LQRSpec, enumerate_policy

TRAINING_TRANSITIONS = 4096
SMOKE_TRANSITIONS = 512
ACTOR_SHAPES = ((16,), (32, 32))
CRITIC_SHAPES = ((32,), (64, 64))
LR_RECIPES = ((3e-4, 1e-3), (1e-3, 3e-3))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def file_binding(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def tree_digest(value):
    """Stable content identity for nested optimizer/model/replay state."""
    h = hashlib.sha256()
    def feed(x):
        if torch.is_tensor(x):
            x = x.detach().cpu().numpy()
        if isinstance(x, np.ndarray):
            h.update(str((x.dtype.str, x.shape)).encode())
            if x.dtype.hasobject:
                feed(x.tolist())
            else:
                h.update(x.tobytes())
        elif isinstance(x, dict):
            for k in sorted(x, key=str):
                feed(k); feed(x[k])
        elif isinstance(x, (list, tuple)):
            h.update(str(type(x)).encode())
            for v in x:
                feed(v)
        else:
            h.update(str((type(x).__name__, x)).encode())
    feed(value)
    return h.hexdigest()


def roster():
    return [dict(actor_hiddens=list(actor), critic_hiddens=list(critic), lr_recipe=recipe)
            for actor in ACTOR_SHAPES for critic in CRITIC_SHAPES for recipe in range(2)]


class FiniteRosterSearcher(RandomSearcher):
    """Finite Cartesian roster; bind its identity in durable state."""
    def __init__(self, search_space, rows):
        super().__init__(search_space, seed=0)
        self.rows = deepcopy(rows)

    def suggest(self):
        if len(self.trials) >= len(self.rows):
            raise RuntimeError('Finite RL-LQR roster exhausted')
        return Config(deepcopy(self.rows[len(self.trials)]))

    def get_state(self):
        return {**super().get_state(), 'finite_roster': deepcopy(self.rows)}

    def set_state(self, state):
        if state.get('finite_roster') != self.rows:
            raise ValueError('Saved finite roster differs')
        super().set_state(state)


def _model_config(config):
    actor, critic = list(config['actor_hiddens']), list(config['critic_hiddens'])
    return dict(fcnet_hiddens=actor, fcnet_activation='tanh',
                head_fcnet_hiddens=actor, head_fcnet_activation='tanh',
                fusionnet_hiddens=critic, fusionnet_activation='tanh',
                actor_hiddens=actor, critic_hiddens=critic,
                critic_fusion_hiddens=critic, critic_activation='tanh')


def _config(config, seed, *, use_gpu=False):
    spec = LQRSpec()
    actor_lr, critic_lr = LR_RECIPES[config['lr_recipe']]
    return (SACConfig().framework('torch')
        .environment(env=FiniteLQREnv, env_config=spec.to_dict(),
                     disable_env_checking=False, clip_actions=False, normalize_actions=False)
        .rl_module(model_config=_model_config(config),
                   rl_module_spec=RLModuleSpec(catalog_class=IndependentSACCatalog))
        .env_runners(num_env_runners=0, num_envs_per_env_runner=1, rollout_fragment_length=64)
        .learners(num_learners=0, num_gpus_per_learner=1 if use_gpu else 0)
        .training(twin_q=True, gamma=spec.gamma, initial_alpha=.01,
                  target_entropy='auto', actor_lr=actor_lr, critic_lr=critic_lr,
                  alpha_lr=3e-4, tau=.005, n_step=1, train_batch_size_per_learner=64,
                  num_steps_sampled_before_learning_starts=64,
                  replay_buffer_config={'type': 'EpisodeReplayBuffer', 'capacity': 1024},
                  training_intensity=1.)
        .reporting(min_sample_timesteps_per_iteration=64, min_time_s_per_iteration=0.)
        .debugging(seed=int(seed), log_level='ERROR'))


def _learner(algo):
    return algo.learner_group._learner


def _module(algo):
    return _learner(algo).module[DEFAULT_MODULE_ID].unwrapped()


def _optimizer_state(algo):
    return {name: optimizer.state_dict() for name, optimizer in
            _learner(algo).get_optimizers_for_module(DEFAULT_MODULE_ID)}


def _updates(algo):
    result = {}
    for name, optimizer in _learner(algo).get_optimizers_for_module(DEFAULT_MODULE_ID):
        steps = [int(s['step'].item()) for s in optimizer.state.values() if 'step' in s]
        result[name] = {'min': min(steps, default=0), 'max': max(steps, default=0),
                        'state_count': len(steps), 'lr': optimizer.param_groups[0]['lr']}
    return result


def parameter_audit(module):
    named = dict(module.named_parameters())
    groups = {prefix: {n: p for n, p in named.items() if n.startswith(prefix)}
              for prefix in ('pi', 'qf', 'qf_twin', 'target_qf')}
    if any(not g for g in groups.values()):
        raise AssertionError('Actor, twin critics and targets must all exist')
    if not all(torch.isfinite(v).all().item() for v in named.values()):
        raise AssertionError('Nonfinite SAC parameter')
    actor = {v.data_ptr() for n, v in named.items() if n.startswith('pi')}
    q = {v.data_ptr() for n, v in named.items() if n.startswith(('qf.', 'qf_encoder.'))}
    twin = {v.data_ptr() for n, v in named.items() if n.startswith('qf_twin')}
    if actor & q or actor & twin or q & twin:
        raise AssertionError('Shared actor/critic parameters')
    return {'parameter_count': sum(p.numel() for p in named.values()),
            'all_parameters_finite': True, 'disjoint_actor_and_critics': True,
            'devices': sorted({str(p.device) for p in named.values()}),
            'shapes': {n: list(v.shape) for n, v in named.items()}}


class PortableActor(torch.nn.Module):
    """Inference-only graph, saved without Ray runtime services."""
    def __init__(self, module):
        super().__init__()
        self.encoder = deepcopy(module.pi_encoder).cpu().eval()
        self.head = deepcopy(module.pi).cpu().eval()

    def forward(self, observation):
        logits = self.head(self.encoder({Columns.OBS: observation})[ENCODER_OUT])
        mean = logits[..., :1]
        return torch.clamp(((torch.tanh(mean)+1.)/2.)*2.-1., -1., 1.)


def actor_policy(actor, spec=LQRSpec()):
    def policy(states, step):
        obs = np.column_stack([states, np.full(len(states), (spec.horizon-step)/spec.horizon)])
        with torch.no_grad():
            return actor(torch.as_tensor(obs, dtype=torch.float32)).cpu().numpy().reshape(-1)
    return policy


def _identities(algo):
    return {'parameters': tree_digest(dict(_module(algo).named_parameters())),
            'optimizers': tree_digest(_optimizer_state(algo)),
            'temperature': tree_digest(_learner(algo).curr_log_alpha[DEFAULT_MODULE_ID]),
            'replay': tree_digest(algo.local_replay_buffer.get_state()),
            'replay_rng': tree_digest(algo.local_replay_buffer.rng.bit_generator.state)}


def _save(algo, output):
    checkpoint = Path(algo.save_to_path((output/'checkpoint').resolve()))
    # New-stack Algorithm checkpoints omit replay and standalone SAC temperature.
    extra = {'replay': algo.local_replay_buffer.get_state(),
             'replay_rng': algo.local_replay_buffer.rng.bit_generator.state,
             'temperature': _learner(algo).curr_log_alpha[DEFAULT_MODULE_ID].detach().cpu(),
             'numpy_rng': np.random.get_state(), 'python_rng': random.getstate(),
             'torch_rng': torch.get_rng_state()}
    with (checkpoint/'lqr-supplement.pkl').open('xb') as f:
        pickle.dump(extra, f)
    write(checkpoint/'lqr-integrity.json', {'identities': _identities(algo),
          'supplement': file_binding(checkpoint/'lqr-supplement.pkl')})
    return checkpoint


def _restore(algo, checkpoint):
    checkpoint = Path(checkpoint)
    integrity = json.loads((checkpoint/'lqr-integrity.json').read_text())
    if file_binding(checkpoint/'lqr-supplement.pkl') != integrity['supplement']:
        raise ValueError('Checkpoint supplement identity differs')
    algo.restore_from_path(checkpoint)
    with (checkpoint/'lqr-supplement.pkl').open('rb') as f:
        extra = pickle.load(f)  # trusted local artifacts only
    algo.local_replay_buffer.set_state(extra['replay'])
    algo.local_replay_buffer.rng.bit_generator.state = extra['replay_rng']
    with torch.no_grad():
        _learner(algo).curr_log_alpha[DEFAULT_MODULE_ID].copy_(extra['temperature'])
    np.random.set_state(extra['numpy_rng']); random.setstate(extra['python_rng'])
    torch.set_rng_state(extra['torch_rng'])
    actual = _identities(algo)
    if actual != integrity['identities']:
        write(checkpoint.parent/'restore-mismatch.json', {'expected': integrity['identities'], 'actual': actual})
        raise AssertionError('Restored model, optimizer, temperature or replay differs')
    return {'identities_equal': True, 'identities': actual, 'bitwise_trajectory_resume': False,
            'limitation': 'Environment-runner RNG/episode continuation is not certified; restored learning state is verified.'}


def fit(config, seed, output, *, transitions=TRAINING_TRANSITIONS, use_gpu=False, restore=None, barrier=None):
    """Fresh fit or bounded resumed segment; counters measure actual work."""
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    started_epoch, started = time.time(), time.monotonic()
    np.random.seed(seed); random.seed(seed); torch.manual_seed(seed); torch.set_num_threads(1)
    if use_gpu and not torch.cuda.is_available():
        raise RuntimeError('Assigned GPU is unavailable')
    if ray.is_initialized():
        raise RuntimeError('Nested Ray state must be absent at fit entry')
    # Linux AF_UNIX paths are limited to 107 bytes. A short alias keeps logs
    # physically within the owned evidence directory and its output cap.
    (output/'ray').mkdir()
    ray_alias = Path('/tmp')/('lqr-'+uuid4().hex[:10])
    ray_alias.symlink_to((output/'ray').resolve(), target_is_directory=True)
    algo = None
    try:
        ray.init(num_cpus=1, num_gpus=1 if use_gpu else 0, include_dashboard=False,
                 log_to_driver=False, object_store_memory=80*1024**2, _temp_dir=str(ray_alias))
        algo = _config(config, seed, use_gpu=use_gpu).build_algo()
        algo.local_replay_buffer.rng = np.random.default_rng(seed+9000)
        restored = _restore(algo, restore) if restore else None
        module = _module(algo)
        before = {n: v.detach().cpu().clone() for n, v in module.named_parameters()}
        before_updates = _updates(algo)
        baseline = algo.local_replay_buffer.get_added_timesteps()
        rows = []
        if barrier is not None:
            barrier = Path(barrier); barrier.mkdir(exist_ok=True)
            (barrier/str(os.getpid())).write_text(str(time.time()))
            deadline = time.monotonic()+120
            while len(list(barrier.iterdir())) != 2:
                if time.monotonic() > deadline:
                    raise TimeoutError('Second GPU learner did not reach the training barrier')
                time.sleep(.02)
        if use_gpu:
            torch.cuda.synchronize()
        training_started_epoch = time.time()
        for iteration in range(transitions//64):
            train = algo.train()
            measured = algo.local_replay_buffer.get_added_timesteps()-baseline
            if measured != (iteration+1)*64:
                raise AssertionError(f'Unexpected sampled work: {measured}')
            rows.append({'iteration': iteration+1, 'sampled_transitions': measured,
                         'updates': _updates(algo),
                         'env_metrics': {k: float(v) for k, v in train.get('env_runners', {}).items()
                                         if 'num_env_steps_sampled' in k and np.isscalar(v)}})
            write(output/'training-progress.json', rows[-1])
        if use_gpu:
            torch.cuda.synchronize()
        training_finished_epoch = time.time()
        if not rows or rows[-1]['sampled_transitions'] != transitions:
            raise AssertionError('Transitions must be positive multiples of 64')
        changes = {prefix: any(not torch.equal(before[n], v.detach().cpu())
                              for n, v in module.named_parameters() if n.startswith(prefix))
                   for prefix in ('pi', 'qf.', 'qf_twin', 'target_qf')}
        if not all(changes.values()):
            raise AssertionError('Actor, both critics and targets must update')
        updates = _updates(algo)
        if set(updates) != {'qf', 'qf_twin', 'policy', 'alpha'} or any(
                v['min'] <= before_updates[n]['max'] for n, v in updates.items()):
            raise AssertionError('Every optimizer must perform nonzero new updates')
        audit = parameter_audit(module)
        if use_gpu != all(d.startswith('cuda') for d in audit['devices']):
            raise AssertionError('Actual learner device differs from allocation')
        actor = PortableActor(module)
        obs = torch.tensor([[-1., 1.], [1., 1.], [.4, .5], [-5., .125]], dtype=torch.float32)
        infer = algo.get_module()
        infer_device = next(infer.parameters()).device
        with torch.no_grad():
            logits = infer.forward_inference({Columns.OBS: obs.to(infer_device)})[Columns.ACTION_DIST_INPUTS]
            expected = infer.get_inference_action_dist_cls().from_logits(logits).to_deterministic().sample().cpu()
            if not torch.allclose(actor(obs), expected, rtol=32*torch.finfo(torch.float32).eps, atol=32*torch.finfo(torch.float32).eps):
                raise AssertionError('Portable and RLlib deterministic actors differ')
        traced = torch.jit.trace(actor, obs)
        traced.save(str(output/'actor.pt'))
        score = enumerate_policy(actor_policy(traced))
        repeated = enumerate_policy(actor_policy(torch.jit.load(str(output/'actor.pt'))))
        if not np.array_equal(score['actions'], repeated['actions']):
            raise AssertionError('Saved deterministic inference does not reproduce')
        np.savez_compressed(output/'paths.npz', **{k: score[k] for k in
                            ('states', 'actions', 'noise', 'path_costs', 'path_advantages')})
        checkpoint = _save(algo, output)
        write(output/'training.json', rows)
        result = {'config': config, 'seed': seed, 'transitions': rows[-1]['sampled_transitions'],
                  'replay_total_added': algo.local_replay_buffer.get_added_timesteps(),
                  'cost': score['cost'], 'optimal_cost': score['optimal_cost'],
                  'optimality_gap': score['gap'], 'identity_error': score['identity_error'],
                  'path_count': score['paths'], 'parameter_audit': audit,
                  'parameter_changes': changes, 'optimizer_before': before_updates, 'optimizer_after': updates,
                  'checkpoint': str(checkpoint), 'restore': restored,
                  'actor': file_binding(output/'actor.pt'), 'paths': file_binding(output/'paths.npz'),
                  'device': audit['devices'], 'pid': os.getpid(),
                  'visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                  'gpu_name': torch.cuda.get_device_name(0) if use_gpu else None,
                  'cpu_affinity': sorted(os.sched_getaffinity(0)),
                  'started_epoch': started_epoch, 'finished_epoch': time.time(),
                  'training_started_epoch': training_started_epoch,
                  'training_finished_epoch': training_finished_epoch,
                  'wall_seconds': time.monotonic()-started, 'train_iterations': len(rows),
                  'claims': {'standard_rllib_torch_sac_losses': True, 'convergence': False,
                             'global_optimality': False, 'economic_effectiveness': False}}
        write(output/'fit-result.json', result)
        print(json.dumps({'fit': str(output), 'cost': result['cost'], 'transitions': result['transitions']}), flush=True)
        return result
    finally:
        if algo is not None:
            algo.stop()
        ray.shutdown()
        ray_alias.unlink()


def objective(config, *, seed, evaluation, execution=None, trial_id=None):
    out = Path(os.environ['HPO_LQR_OUTPUT'])/'fits'/str(trial_id or seed)
    if evaluation.role == 'final' and not (out.parents[1]/'study'/'selection-freeze.json').is_file():
        raise ValueError('Final training requires the durable selection freeze')
    result = fit(config, seed, out)
    return {'value': result['cost'], 'cost': float(result['transitions']),
            'metadata': {'resource': {'unit': 'environment_transitions', 'work': result['transitions']},
                         'device': result['device'], 'role': evaluation.role,
                         'optimality_gap': result['optimality_gap'],
                         'artifacts': {'fit': str((out/'fit-result.json').relative_to(Path(os.environ['HPO_LQR_OUTPUT'])))}}}


def declaration():
    return StudyDeclaration(objective_id='finite-stochastic-lqr-cost:v1', model_id='rllib-torch-sac:v1',
        data_id='enumerated-binary-noise-law:v1', protocol_id='known-answer-complete-paths:v1',
        objectives=(EvaluationObjective('cost', 'min', 'discounted_quadratic_cost'),),
        tuning_folds=(EvaluationFold('tuning-known-law', ('all-dynamics-law',), ('tuning-score',), mode='known_answer'),),
        final_folds=(EvaluationFold('final-known-law', ('all-dynamics-law-final',), ('final-score',), mode='known_answer'),),
        tuning_seeds=(1101, 1102), final_seeds=(2101, 2102))


class LQRStudy(Study):
    def save_checkpoint(self):
        super().save_checkpoint()
        if self._evaluation and self._evaluation.state['phase'] == 'selection_frozen':
            path = self.checkpoint_dir/'selection-freeze.json'
            if not path.exists():
                write(path, {'epoch': time.time(), 'selection': deepcopy(self._evaluation.state['selection']),
                             'snapshot': self._snapshot()})


def space_and_budget():
    space = SearchSpace([Knob('actor_hiddens', 'categorical', [list(x) for x in ACTOR_SHAPES]),
                         Knob('critic_hiddens', 'categorical', [list(x) for x in CRITIC_SHAPES]),
                         Knob('lr_recipe', 'categorical', [0, 1])])
    budget = StudyBudget(configurations=8, work_unit='environment_transitions',
                         tuning_work=8*2*TRAINING_TRANSITIONS, final_work=2*TRAINING_TRANSITIONS,
                         max_work_per_call=TRAINING_TRANSITIONS, worker_capacity=2,
                         full_run_work=TRAINING_TRANSITIONS)
    return space, budget


def joint(out):
    out = Path(out)
    space, budget = space_and_budget()
    def make(executor, fn):
        return LQRStudy(FiniteRosterSearcher(space, roster()), executor, fn, budget=8, maximize=False,
                        study_name='rl-lqr-joint', checkpoint_dir=out/'study', max_concurrent=2,
                        declaration=declaration(), resource_budget=budget, evaluation_workers=2)
    with ResourceExecutor(2, resources=ResourceSpec(cpu_cores=1, threads=1),
                           cpu_ids=sorted(os.sched_getaffinity(0))[-2:], timeout=600) as executor:
        study = make(executor, objective)
        result = study.run().to_dict()
    write(out/'joint-result.json', result)
    before = {str(p): file_binding(p) for p in out.glob('fits/*/fit-result.json')}
    def forbidden(config, *, seed, evaluation, execution=None, trial_id=None):
        raise AssertionError('Completed Study resume attempted new objective work')
    executor = ResourceExecutor(2, resources=ResourceSpec(cpu_cores=1, threads=1),
                                cpu_ids=sorted(os.sched_getaffinity(0))[-2:])
    try:
        resumed = make(executor, forbidden)
        resumed.load_checkpoint(out/'study'/'rl-lqr-joint_checkpoint.json')
        replayed = resumed.run().to_dict()
        if executor._prepared or replayed != result:
            raise AssertionError('Completed resume changed results or dispatched workers')
    finally:
        executor.shutdown()
    after = {str(p): file_binding(p) for p in out.glob('fits/*/fit-result.json')}
    if before != after or len(after) != 18:
        raise AssertionError('Joint study must retain exactly 18 unchanged fits')
    write(out/'study-resume.json', {'same_result': True, 'new_dispatches': 0, 'fit_count': len(after)})
    return result


def hardware(out):
    out = Path(out)
    def one(row, execution):
        config, seed, name = row
        result = fit(config, seed, out/name, transitions=SMOKE_TRANSITIONS, use_gpu=True, barrier=out/'ready')
        result['execution'] = execution.to_dict()
        return result
    with ResourceExecutor(2, resources=ResourceSpec(cpu_cores=1, threads=1, gpus=1),
                           cpu_ids=sorted(os.sched_getaffinity(0))[-2:], gpu_ids=('0', '1'), timeout=550) as executor:
        assigned_devices = [p.gpu_ids[0] for p in executor.placements]
        results = executor.map(one, [(roster()[0], 3101, 'gpu-0'), (roster()[-1], 3102, 'gpu-1')])
    overlap = min(r['training_finished_epoch'] for r in results)-max(r['training_started_epoch'] for r in results)
    devices = [r['visible_devices'] for r in results]
    write(out/'hardware-observations.json', {'results':results, 'overlap_seconds':overlap,
                                            'assigned_gpu_uuids':assigned_devices})
    if overlap <= 0 or len({r['pid'] for r in results}) != 2 or len(set(devices)) != 2:
        raise AssertionError('Actual independent GPU workers did not overlap')
    if set(devices) != set(assigned_devices) or any(r['device'] != ['cuda:0'] for r in results):
        raise AssertionError('GPU visibility or actual learner tensors differ from allocation')
    record = {'results': results, 'overlap_seconds': overlap, 'distinct_gpu_ids': devices,
              'assigned_gpu_uuids': assigned_devices,
              'transitions_per_fit': SMOKE_TRANSITIONS,
              'claims': {'actual_parallel_gpu_execution': True, 'bg_pbt': False, 'economic_effectiveness': False}}
    write(out/'hardware-result.json', record)
    return record


def replay_joint(out):
    """Read-only completion repair of the consumed 18-fit allocation."""
    out = Path(out)
    source = out.parent/'20261027T093013Z-joint-fd36a47a'
    original = json.loads((source/'joint-result.json').read_text())
    before = {str(p): file_binding(p) for p in source.rglob('*') if p.is_file()}
    space, budget = space_and_budget()
    def forbidden(config, *, seed, evaluation, execution=None, trial_id=None):
        raise AssertionError('Completed Study resume attempted objective work')
    executor = ResourceExecutor(2, resources=ResourceSpec(cpu_cores=1, threads=1),
                                cpu_ids=sorted(os.sched_getaffinity(0))[-2:])
    try:
        resumed = LQRStudy(FiniteRosterSearcher(space, roster()), executor, forbidden, budget=8, maximize=False,
                           study_name='rl-lqr-joint', checkpoint_dir=out/'restored-study', max_concurrent=2,
                           declaration=declaration(), resource_budget=budget, evaluation_workers=2)
        resumed.load_checkpoint(source/'study'/'rl-lqr-joint_checkpoint.json')
        replayed = resumed.run().to_dict()
        write(out/'replayed-result.json', replayed)
        write(out/'original-result.json', original)
        differences = []
        def compare(a, b, path=''):
            if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b):
                for k in a:
                    compare(a[k], b[k], path+'/'+k)
            elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                for i, (x,y) in enumerate(zip(a,b)):
                    compare(x,y,path+'/'+str(i))
            elif a != b:
                differences.append({'path':path, 'original':a, 'restored':b})
        compare(original, replayed)
        write(out/'resume-differences.json', differences)
        if executor._prepared:
            raise AssertionError('Completed resume dispatched workers')
    finally:
        executor.shutdown()
    after = {str(p): file_binding(p) for p in source.rglob('*') if p.is_file()}
    if before != after:
        raise AssertionError('Read-only replay changed original evidence')
    if differences:
        raise AssertionError('Completed-resume difference: '+differences[0]['path'])
    write(out/'joint-replay-result.json', {'passed':True, 'source':str(source), 'fit_count':18,
          'new_dispatches':0, 'new_transitions':0, 'original_evidence_unchanged':True,
          'differences':differences, 'meaning':'All result records exactly identical; no worker startup.'})


def execute(op, out):
    out = Path(out)
    if op == 'learner':
        initial = fit(roster()[0], 4101, out/'initial', transitions=SMOKE_TRANSITIONS)
        resumed = fit(roster()[0], 4101, out/'resumed', transitions=SMOKE_TRANSITIONS, restore=initial['checkpoint'])
        if resumed['replay_total_added'] != 1024 or not resumed['restore']['identities_equal']:
            raise AssertionError('Resumed work or state mismatch')
        write(out/'learner-result.json', {'initial': initial, 'resumed': resumed, 'total_transitions': 1024})
    elif op == 'joint':
        joint(out)
    elif op == 'hardware':
        hardware(out)
    elif op == 'joint-replay':
        replay_joint(out)
