"""Descriptive paired ranks from the tuning ledger, without imputation."""
from collections import Counter, defaultdict
import math


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def midranks(values):
    """One-based average ranks; exact equal measurements form a tie."""
    if not all(_finite(value) for value in values):
        raise ValueError('Ranks require finite measurements')
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for index in ordered[start:end]:
            ranks[index] = (start + 1 + end) / 2
        start = end
    return ranks


def _correlation(pairs):
    x = midranks([p['rung_value'] for p in pairs])
    y = midranks([p['full_value'] for p in pairs])
    for pair, xr, yr in zip(pairs, x, y):
        pair.update(rung_rank=xr, full_rank=yr)
    if len(pairs) < 2:
        return None, 'insufficient_pairs'
    center = (len(pairs) + 1) / 2
    xx = math.fsum((v-center)**2 for v in x)
    yy = math.fsum((v-center)**2 for v in y)
    if not xx or not yy:
        return None, 'constant_ranks'
    xy = math.fsum((a-center)*(b-center) for a, b in zip(x, y))
    return max(-1., min(1., xy / math.sqrt(xx*yy))), 'defined'


def paired_rung_diagnostics(state):
    """Reconstruct per-metric Spearman correlations against declared full fidelity.

    Only the Study tuning trial/result/progress ledgers are read. The separate
    final-evaluation records are never input. Pairing requires recorded root
    lineage and unchanged configuration. This is an observed-pair description,
    not a pruning-safety test, an unbiased estimate, or a scheduler selector.
    """
    report = dict(schema='paired_rung_diagnostics_v1', study_id=state['study_name'],
                  scope='observed_tuning_pairs', full_fidelity=None, rows=[])
    scheduler = state.get('scheduler_state')
    if not scheduler:
        return {**report, 'status': 'not_applicable', 'reason': 'no_scheduler'}
    full = scheduler.get('config', {}).get('r_max')
    if not _finite(full) or full <= 0:
        return {**report, 'status': 'unavailable', 'reason': 'missing_declared_full_fidelity'}
    report['full_fidelity'] = full
    inner = scheduler.get('scheduler', scheduler)
    rungs = inner.get('rungs')
    if (not isinstance(rungs, list) or not rungs or
            any(not _finite(r) or not 0 < r <= full for r in rungs) or
            rungs != sorted(set(rungs)) or rungs[-1] != full):
        return {**report, 'status': 'unavailable', 'reason': 'missing_or_invalid_rung_grid'}
    trials, results = state['trials'], state['results']
    roots = state.get('roots')
    if (not isinstance(roots, dict) or set(roots) != set(trials) or
            any(root not in trials or roots.get(root) != root for root in roots.values())):
        return {**report, 'status': 'unavailable', 'reason': 'missing_or_invalid_root_lineage'}
    vector = state.get('multi_objective')
    if vector:
        from hponas.multi_objective import ObjectiveSpec
        spec = ObjectiveSpec(**vector['contract'])
        if spec.identity != vector['identity']:
            raise ValueError('Diagnostic objective contract identity differs')
        metrics = [(m['name'], m['direction']) for m in spec.contract['objectives']]
    else:
        declared = (state.get('evaluation') or {}).get('contract', {}).get('objectives', [])
        metrics = [(declared[0]['name'] if declared else 'value', 'max' if state['maximize'] else 'min')]
    by_root = defaultdict(list)
    for tid, root in roots.items():
        by_root[root].append(tid)

    def disposition(root, tids):
        terminal = inner.get('terminal', {}).get(root)
        if terminal:
            return terminal
        if root in inner.get('vetoed_trials', []):
            return 'vetoed'
        latest = max(tids, key=lambda tid: trials[tid]['fidelity'])
        row = results.get(latest)
        if row and row['status'] != 'completed':
            return row['status']
        if any(tid in state.get('pending', []) for tid in tids):
            return 'pending'
        return 'finished_without_full_result' if state.get('finished') else 'awaiting_promotion'

    def measurement(root, tids, fidelity, name):
        if any(trials[tid]['config']['values'] != trials[root]['config']['values'] for tid in tids):
            return None, 'configuration_changed'
        observed, rejected = [], []
        for tid in tids:
            row = results.get(tid)
            if row is not None and row['fidelity'] == fidelity:
                meta = row.get('metadata', {})
                if meta.get('evaluation', {}).get('role', 'tuning') != 'tuning':
                    rejected.append('non_tuning_role')
                elif row['status'] != 'completed':
                    rejected.append(row['status'])
                else:
                    payload = meta.get('multi_objective', {})
                    value = (payload.get('objectives') or {}).get(name) if vector else row['objective_value']
                    if vector and payload.get('status') != 'completed':
                        rejected.append('invalid_vector_measurement')
                    elif not _finite(value):
                        rejected.append('nonfinite_or_missing_measurement')
                    else:
                        observed.append(dict(value=value, trial_id=tid, source='endpoint',
                                             feasible=payload.get('feasible') if vector else None))
            # Full fidelity requires a successfully completed endpoint. A last
            # progress report followed by a crash/failure is not that endpoint.
            if fidelity == full or vector:
                continue
            parent = trials[tid].get('parent_trial_id')
            if parent in trials and fidelity <= trials[parent]['fidelity']:
                continue  # A restarted promotion repeats this prefix.
            for step, progress in state.get('report_cache', {}).get(tid, {}).items():
                if float(step) != fidelity:
                    continue
                value = progress.get('value')
                if not _finite(value):
                    rejected.append('nonfinite_or_missing_measurement')
                else:
                    observed.append(dict(value=value, trial_id=tid, source='progress', feasible=None))
        if observed:
            if len({r['value'] for r in observed}) != 1:
                return None, 'conflicting_measurements'
            return dict(value=observed[0]['value'], sources=observed), None
        if rejected:
            return None, '+'.join(sorted(set(rejected)))
        explicit = disposition(root, tids)
        return None, explicit if explicit in {'failed','cancelled','pruned','vetoed','pending'} else 'not_evaluated'

    for rung in rungs[:-1]:
        for name, direction in metrics:
            pairs, exclusions = [], []
            n_rung = n_full = 0
            for root, tids in sorted(by_root.items()):
                low, low_reason = measurement(root, tids, rung, name)
                high, high_reason = measurement(root, tids, full, name)
                n_rung += low is not None
                n_full += high is not None
                if low is not None and high is not None:
                    pairs.append(dict(root_trial_id=root, rung_value=low['value'], full_value=high['value'],
                                      rung_sources=low['sources'], full_sources=high['sources']))
                else:
                    exclusions.append(dict(root_trial_id=root, rung_reason=low_reason, full_reason=high_reason,
                                           disposition=disposition(root, tids)))
            rho, reason = _correlation(pairs)
            counts = Counter(f'{side}:{row[side+"_reason"]}' for row in exclusions
                             for side in ('rung','full') if row[side+'_reason'] is not None)
            report['rows'].append(dict(fidelity=rung, objective=name, direction=direction,
                full_fidelity=full, spearman=rho, status=reason, n_roots=len(by_root),
                n_rung_observed=n_rung, n_full_observed=n_full, n_pairs=len(pairs),
                n_excluded=len(exclusions), exclusion_counts=dict(sorted(counts.items())),
                pairs=pairs, exclusions=exclusions))
    return {**report, 'status': 'available' if report['rows'] else 'not_applicable',
            'reason': None if report['rows'] else 'no_lower_rungs'}


def read_rung_diagnostics(state):
    """Reconstruct a report and refuse a conflicting retained projection."""
    if state is None:
        return None
    report = paired_rung_diagnostics(state)
    if 'rung_diagnostics' in state and state['rung_diagnostics'] != report:
        raise ValueError('Stored rung diagnostics differ from the tuning ledger')
    return report
