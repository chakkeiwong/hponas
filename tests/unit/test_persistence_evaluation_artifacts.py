"""Artifact identity survives repeated evaluation and durable store recovery."""
from contextlib import closing
from copy import deepcopy

import pytest

from hponas import Study, StudyDeclaration, EvaluationFold, EvaluationObjective
from hponas import RandomSearcher, LocalExecutor, Knob, SearchSpace
from hponas.persistence import snapshot_artifacts
from hponas.store import Store


def test_tuning_and_final_artifact_types_are_disjoint_and_queryable_after_reopen(tmp_path):
    declaration = StudyDeclaration(objective_id='loss', model_id='model', data_id='synthetic', protocol_id='v1',
        objectives=(EvaluationObjective('loss','min','units'),),
        tuning_folds=(EvaluationFold('tune',('train',),('validate',)),), tuning_seeds=(1,2),
        final_folds=(EvaluationFold('heldout',('train',),('test',)),), final_seeds=(3,))
    def objective(config, seed, evaluation, trial_id):
        return {'value':float(seed), 'artifacts':{'model':str(tmp_path/(trial_id+'.bin'))}}
    database = tmp_path/'artifacts.db'
    with closing(Store(database)) as store:
        study = Study(RandomSearcher(SearchSpace([Knob('x','ordinal',(0,1))]),seed=2),
            LocalExecutor(), objective, declaration=declaration, budget=1,
            maximize=False, study_name='artifacts', store=store)
        study.run()
        state = study._snapshot()
        tid = 'artifacts_trial_0'
        tuning = state['evaluation']['tuning'][tid]
        final = state['evaluation']['final'][tid]
        expected = {row['result']['trial_id']+':model':str(tmp_path/(row['result']['trial_id']+'.bin')) for row in tuning}
        expected['final:'+final[0]['result']['trial_id']+':model'] = str(tmp_path/(final[0]['result']['trial_id']+'.bin'))
        assert len(expected) == 3
        store.save_study_snapshot(state)
    with closing(Store(database)) as reopened:
        assert {r['artifact_type']:r['path'] for r in reopened.read_artifacts(tid)} == expected
        for kind, path in expected.items():
            assert [r['path'] for r in reopened.read_artifacts(tid, kind)] == [path]


@pytest.mark.parametrize('role', ['tuning','final'])
def test_snapshot_projection_tolerates_repetitions_without_optional_metadata(role):
    state={'results':{}, 'evaluation':{'tuning':{},'final':{}}}
    state['evaluation'][role]['candidate'] = [{'result':{'trial_id':'rep-1'}},
        {'result':{'trial_id':'rep-2','metadata':{}}},
        {'result':{'trial_id':'rep-3','metadata':{'artifacts':{'model':'model.bin'}}}}]
    before=deepcopy(state)
    assert snapshot_artifacts(state,'candidate') == [
        (('final:' if role=='final' else '')+'rep-3:model','model.bin')]
    assert state == before
