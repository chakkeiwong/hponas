"""Terminal suggestion refusals stop once and retain the observable study prefix."""
import json

import pytest

from hponas import IncompleteStudyError, LocalExecutor, RandomSearcher, Study
from hponas.events import EventLog
from hponas.searchers.base import SearchBudgetExhaustedError, SearchSpaceExhaustedError
from hponas.space import Knob, SearchSpace
from hponas.types import Config


@pytest.mark.parametrize('exception,reason,event_type', [
    (SearchSpaceExhaustedError, 'search_space_exhausted', 'search_exhausted'),
    (SearchBudgetExhaustedError, 'search_budget_exhausted', 'search_budget_exhausted'),
])
@pytest.mark.parametrize('completed_prefix', [0, 1])
def test_terminal_suggestion_is_not_retried_and_preserves_durable_result(
        tmp_path, exception, reason, event_type, completed_prefix):
    class FiniteSearcher(RandomSearcher):
        calls = 0

        def suggest(self):
            self.calls += 1
            if self.calls <= completed_prefix:
                return Config({'x': .25})
            if self.calls == completed_prefix + 1:
                raise exception('Declared finite search is exhausted')
            pytest.fail('A terminal suggestion was retried')

    evaluations = []

    def objective(config):
        evaluations.append(dict(config))
        return config['x']

    searcher = FiniteSearcher(SearchSpace([Knob('x', 'continuous', (0., 1.))]), seed=11)
    study = Study(searcher, LocalExecutor(), objective, budget=3,
                  max_concurrent=1, study_name='terminal', checkpoint_dir=tmp_path,
                  event_log=EventLog(tmp_path/'events.jsonl'))
    if completed_prefix:
        result = study.run()
        assert result.best_value == .25 and result.best_config.values == {'x': .25}
        assert result.status == reason
    else:
        with pytest.raises(IncompleteStudyError) as raised:
            study.run()
        result = raised.value.result
        assert result.best_config is None and result.best_value is None
        assert result.status == 'incomplete'
    assert result.reason == reason and result.n_trials == completed_prefix
    assert len(result.history) == completed_prefix
    assert searcher.calls == completed_prefix + 1
    assert evaluations == [{'x': .25}] * completed_prefix
    checkpoint = json.loads((tmp_path/'terminal_checkpoint.json').read_text())
    assert checkpoint['stop_reason'] == reason and checkpoint['finished'] is True
    assert checkpoint['pending'] == []
    assert len(checkpoint['trials']) == len(checkpoint['results']) == completed_prefix
    events = [json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    terminal = [row for row in events if row['event_type'] == event_type]
    assert len(terminal) == 1
    assert terminal[0]['data']['schema_version'] == 1
