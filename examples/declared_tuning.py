"""Small declared workflow with an analytic tuning answer; no external data."""
from contextlib import closing
import json
from pathlib import Path
import tempfile

from hponas import (EvaluationFold, EvaluationObjective, LocalExecutor, Knob,
                    RandomSearcher, SearchSpace, Study, StudyDeclaration, StudyBudget)
from hponas.store import Store


def make_study(directory, store=None):
    declaration = StudyDeclaration(
        objective_id='quadratic-with-centered-seed-offset:v1', model_id='scalar-coordinate:v1',
        data_id='analytic-generator:v1', protocol_id='separate-offsets:v1',
        objectives=(EvaluationObjective('loss', 'min', 'squared_distance'),),
        tuning_folds=(EvaluationFold('tune', ('train',), ('validation',), mode='known_answer'),),
        final_folds=(EvaluationFold('final', ('train', 'validation'), ('sealed',), mode='known_answer'),),
        tuning_seeds=(2, 4), final_seeds=(12, 14))

    def objective(config, seed, evaluation, trial_id):
        # Paired offsets cancel exactly; the analytic optimum is x=2, loss=0.
        # Search may miss it, so report the actual regret without a threshold.
        center = 3 if evaluation.role == 'tuning' else 13
        artifact = Path(directory) / (trial_id + '-model.json')
        artifact.write_text(json.dumps({'schema':'scalar-coordinate-v1','x':config['x'],
                                       'role':evaluation.role,'seed':seed})+'\n')
        return {'value': (config['x'] - 2.) ** 2 + (seed - center) / 4.,
                'artifacts': {'model': str(artifact)},
                'metadata': {'resource': {'work': 1, 'unit': 'analytic_evaluations'}}}

    return Study(RandomSearcher(SearchSpace([Knob('x', 'ordinal', (0, 4))]), seed=7),
                 LocalExecutor(), objective, budget=8, maximize=False,
                 study_name='declared_example', declaration=declaration,
                 resource_budget=StudyBudget(configurations=8, work_unit='analytic_evaluations',
                    tuning_work=16, final_work=2, max_work_per_call=1, full_run_work=1),
                 checkpoint_dir=directory, store=store)


def run(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with closing(Store(directory / 'study.db')) as store:
        result = make_study(directory, store).run()
        report = result.to_dict()
        report['analytic_reference'] = {'x': 2, 'loss': 0., 'search_regret': result.best_value}
        study_report = store.export_report('declared_example', directory / 'report.json')
        report['workflow_report_schema'] = study_report['schema']
        return report


if __name__ == '__main__':
    destination = Path(tempfile.mkdtemp(prefix='hponas-declared-'))
    outcome = run(destination)
    print(json.dumps({'directory': str(destination), 'selection': outcome['best_config'],
                      'evaluation': outcome['evaluation']['outcome'],
                      'reference': outcome['analytic_reference']}, indent=2))
