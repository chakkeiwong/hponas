"""Admission is explicit and a reason cannot change across recovery."""
from copy import deepcopy
from contextlib import closing
import json

import pytest

from hponas import (Study, RandomSearcher, SearchSpace, Knob, LocalExecutor,
                    StudyDeclaration, EvaluationFold, EvaluationObjective)
from hponas.store import Store


def make(**kwargs):
    return Study(RandomSearcher(SearchSpace([Knob('x', 'ordinal', (0, 1))])),
                 LocalExecutor(), lambda c: c['x'], budget=1, study_name='policy', **kwargs)


@pytest.mark.parametrize('reason', [None, '', '  ', False, 3])
def test_undeclared_admission_requires_nonempty_reason(reason):
    with pytest.raises(ValueError, match='^Study requires a declaration or an explicit nonempty legacy_reason$'):
        make(legacy_reason=reason)


def test_declaration_and_legacy_reason_are_mutually_exclusive():
    declaration = StudyDeclaration('objective', 'model', 'data', 'protocol',
        (EvaluationObjective('loss', 'max', 'units'),),
        (EvaluationFold('tuning', ('a',), ('b',)),), (),
        final_seeds=(), opt_out_reason='Exposed arithmetic reference')
    with pytest.raises(ValueError, match='^A declared Study cannot also supply legacy_reason$'):
        make(declaration=declaration, legacy_reason='Conflicting claim')


def test_reason_is_durable_in_all_reporting_surfaces_and_cannot_drift(tmp_path):
    reason = 'Exposed arithmetic admission fixture; no protected score'
    with closing(Store(tmp_path/'study.db')) as store:
        source = make(legacy_reason=reason, store=store)
        result = source.run()
        assert result.evaluation['reason'] == reason
        assert store.read_evaluation('policy')['reason'] == reason
        saved = source._snapshot()
    target = make(legacy_reason=reason)
    path = tmp_path/'checkpoint.json'
    path.write_text(json.dumps(saved))
    target.load_checkpoint(path)
    assert target.evaluation_report() == result.evaluation
    for replacement in ['Different reason', None]:
        altered = deepcopy(saved)
        if replacement is None:
            altered.pop('legacy_reason')
        else:
            altered['legacy_reason'] = replacement
        path.write_text(json.dumps(altered))
        before = target._snapshot()
        with pytest.raises(ValueError, match='legacy_reason differs'):
            target.load_checkpoint(path)
        assert target._snapshot() == before
