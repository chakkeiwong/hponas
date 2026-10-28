from pathlib import Path
import sys
from hponas_rl_lqr_repair import experiments as e

def main():
    op,out=sys.argv[1],Path(sys.argv[2])
    if not out.resolve().is_relative_to(e.BASE) or not out.is_dir():raise ValueError('Fixed output required')
    if op in ('engineering','handoff-engineering','joint-engineering'):
        import pytest
        code=pytest.main([str(e.ROOT/'extensions/rl-lqr-repair/tests'/({'engineering':'test_contracts.py','handoff-engineering':'test_transfer.py','joint-engineering':'test_joint.py'}[op])),'-q','--disable-warnings'])
        if code:raise RuntimeError('Engineering tests failed')
        e.write(out/(op+'-result.json'),dict(passed=True,roster='extensions/rl-lqr-repair/tests',qualification='Engineering only'))
    elif op=='joint':
        from hponas_rl_lqr_repair.joint import main as joint_main
        joint_main(out)
    elif op in ('audit','master-audit'):
        from hponas_rl_lqr_repair import audit
        getattr(audit,op.replace('-','_'))(out)
    else:getattr(e,op.replace('-','_'))(out)
if __name__=='__main__':main()
