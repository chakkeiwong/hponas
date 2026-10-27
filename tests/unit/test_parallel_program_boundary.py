"""Historical completion cannot certify changed source or bypass qualification."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from tools.product_trace import validate_trace

ROOT=Path(__file__).resolve().parents[2]


def test_registered_successor_preserves_historical_evidence_only():
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    validate_trace(ROOT,program)
    assert program['continuation']['steps'][-1]['id']=='GAP-01/FINAL-AUDIT'
    assert program['review_register']['historical_product_baseline']['successor']=='PAR-QUAL-01'


@pytest.mark.parametrize('damage',['package','digest','successor','terminal','gap','dependency'])
def test_stale_source_cannot_use_false_historical_completion(damage):
    p=json.loads((ROOT/'docs/program/program.json').read_text())
    baseline=p['review_register']['historical_product_baseline']
    if damage=='package':baseline['package']='E-PAR01-PLAN'
    if damage=='digest':baseline['source_digest']='0'*64
    if damage=='successor':next(w for w in p['work_items'] if w['id']=='PAR-QUAL-01')['state']='complete'
    if damage=='terminal':next(s for s in p['continuation']['steps'] if s['id']=='PAR-QUAL-01/EXECUTE')['state']='complete'
    if damage=='gap':p['continuation']['steps'][-1]['state']='complete'
    if damage=='dependency':p['continuation']['steps'][-1]['dependencies'].remove('PAR-QUAL-01/EXECUTE')
    with pytest.raises(ValueError,match='stale'):validate_trace(ROOT,p)
