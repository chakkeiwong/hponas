"""Small mean/variance tuning through the public vector Study API."""
import json
from pathlib import Path
import tempfile

from hponas import (Knob, SearchSpace, LocalExecutor, MultiObjectiveStudy, MultiObjectiveRandomSearcher,
                    StudyDeclaration, EvaluationFold, EvaluationObjective, StudyBudget)
from hponas.store import Store
from workloads.finance_portfolio import evaluate

OBJECTIVES = [{'name': 'variance', 'direction': 'min', 'lower': 0., 'upper': 4.},
              {'name': 'expected_return', 'direction': 'max', 'lower': 1., 'upper': 2.}]
CONTRACT = {'objectives': OBJECTIVES, 'constraints': {}, 'work_unit': 'projected_gradient_updates'}


def objective(config, seed, evaluation):
    result = evaluate(config, 8)
    return {'objectives': {k: result[k] for k in ['variance', 'expected_return']},
            'constraints': {}, 'work': result['incremental_updates']}


def run(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    space = SearchSpace([Knob('learning_rate', 'categorical', [0.02, 0.05, 0.1, 0.15]),
                         Knob('return_preference', 'categorical', [0, 1, 2, 4, 8, 12])])
    searcher = MultiObjectiveRandomSearcher(space, **CONTRACT, seed=31)
    store = Store(directory/'finance.sqlite')
    try:
        declaration = StudyDeclaration(objective_id='two-asset-moments:v1', model_id='projected-gradient:v1',
            data_id='finite-equal-moment-designs:v1', protocol_id='deterministic-known-answer:v1',
            objectives=(EvaluationObjective('variance','min','return_squared'),
                        EvaluationObjective('expected_return','max','return')),
            tuning_folds=(EvaluationFold('tuning',('training-moments',),('evaluation-design',),mode='known_answer'),),
            tuning_seeds=(0,), final_folds=(), final_seeds=(),
            opt_out_reason='Deterministic known-answer numerical fixture; no statistical generalization claim.')
        study = MultiObjectiveStudy(searcher, LocalExecutor(), objective, **CONTRACT,
            budget=8, study_name='finite-finance', checkpoint_dir=directory, store=store,
            declaration=declaration, resource_budget=StudyBudget(configurations=8,
                work_unit=CONTRACT['work_unit'],tuning_work=64,final_work=0,max_work_per_call=8,full_run_work=8))
        result = study.run().to_dict()
        study.export_report(directory/'workflow-report.json')
        result.update(task='two_asset_known_moment_portfolio', scientific_acceptance=False,
                      real_market_evidence=False)
        return result
    finally:
        store.close()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hponas-finance-') as directory:
        result = run(directory)
        print(json.dumps({'trials': result['n_trials'], 'metrics': result['metrics'],
                          'scientific_acceptance': False}, indent=2))
