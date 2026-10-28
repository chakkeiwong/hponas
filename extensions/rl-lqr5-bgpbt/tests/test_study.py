import os
from pathlib import Path

from hponas.executors.resource_executor import ResourceExecutor
from hponas.executors.resources import ResourceSpec
from hponas_rl_bgpbt.study import population_search


def test_real_population_generation_halving_and_no_training_replay(tmp_path):
    with ResourceExecutor(2,resources=ResourceSpec(),cpu_ids=sorted(os.sched_getaffinity(0))[:2],
                          timeout=180) as executor:
        result=population_search(tmp_path/'study',executor,1024,seed=37)
        ledger=Path(os.environ['HPONAS_SAC_WORK_LEDGER'])
        before=ledger.read_bytes()
        again=population_search(tmp_path/'study',executor,1024,seed=37)
    assert result==again
    assert ledger.read_bytes()==before
    assert result['work']['bgpbt']['transitions']==result['work']['baseline']['transitions']==4096
    assert result['work']['bgpbt']['gradient_components']==result['work']['baseline']['gradient_components']
    assert result['work']['bgpbt']['distillation_updates']==160
    assert [e['kind'] for e in result['events']]==['compatible_exploit','architecture_generation','compatible_exploit']
    assert len(result['events'][1]['kept'])==2
    assert len(result['population_results'])==24
    assert result['confirmation']['seeds']==[801,802,803]
    assert result['confirmation']['lineage_replay'] is False
