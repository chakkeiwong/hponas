"""Current-source finite capability gate, separate from whole-product release."""
from pathlib import Path
import json

from tools.program_state import ROOT, campaign_view, check
from tools.source_identity import source_digest
from validation.protocol_identity import protocol_path
from validation.tier1_contract import ENTRIES
from validation.tier1_campaign import require_phase
from validation.v16_audit_enforcer import V16Enforcer


def evaluate():
    errors,view=check()
    program=view.get('program',{})
    criteria=[]
    if errors:
        return {'passed':False,'criteria':[{'entry':'program','passed':False,'reason':'; '.join(errors)}],
                'integrated_release_accepted':False}
    receipts=program.get('tier1_campaign_receipts',{})
    if set(receipts)!=set(ENTRIES):
        return {'passed':False,'criteria':[{'entry':'roster','passed':False,'reason':'Complete exact Tier-1 receipts required'}],
                'integrated_release_accepted':False}
    before=source_digest()
    for entry in ENTRIES:
        try:
            phase=require_phase(entry)
            receipt=receipts[entry]
            run=ROOT/receipt['run']
            if run.resolve()!=Path(phase['run_path']):
                raise ValueError('Evidence is not the one frozen allocation')
            retained=campaign_view(ROOT,entry,receipt,before)
            if not retained['fresh']:
                raise ValueError('Stale capability receipt')
            # Recompute from the frozen raw evidence, not receipt PASS labels.
            audit=V16Enforcer(protocol_path(entry)).audit_execution(run)
            result=json.loads((run/'results.json').read_text())
            passed=audit.passed and result.get('verdict')=='PASS'
            criteria.append({'entry':entry,'passed':passed,'verdict':result.get('verdict'),
                             'audit':audit.to_dict()})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            criteria.append({'entry':entry,'passed':False,'reason':str(exc)})
    if before!=source_digest():
        criteria.append({'entry':'source','passed':False,'reason':'Source changed during gate reconstruction'})
    return {'passed':all(row['passed'] for row in criteria),'criteria':criteria,'source_digest':before,
            'scope':'eight_exposed_finite_opt_in_capabilities', 'default_activation':False,
            'integrated_release_accepted':False,
            'release_reason':'Archived Tier-0 acceptance does not transfer to current source; current Tier-0 receipt freshness and release prerequisites are separate.'}
