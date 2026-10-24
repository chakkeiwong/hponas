"""Run: python manual_user_example.py /tmp/new-caller-study"""
from contextlib import closing
from pathlib import Path
import sys
from hponas.quickstart import make_study
from hponas.store import Store

directory = Path(sys.argv[1])
directory.mkdir(exist_ok=False)
with closing(Store(directory / 'study.sqlite')) as store:
    study = make_study('hinge', directory, store)
    result = study.run()
    study.export_report(directory / 'report.json')
    print(result.best_config.values, result.best_value)
    print(result.evaluation['outcome'])

    resumed = make_study('hinge', directory, store)
    resumed.load_checkpoint()
    same_result = resumed.run()
    assert same_result.best_value == result.best_value
