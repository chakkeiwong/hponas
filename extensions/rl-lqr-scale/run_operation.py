from pathlib import Path
import sys
from hponas_rl_lqr_scale import experiments as e

def main():
    op,out=sys.argv[1],Path(sys.argv[2])
    if not out.resolve().is_relative_to(e.BASE) or not out.is_dir():raise ValueError('Fixed output required')
    if op=='engineering':
        import pytest
        if pytest.main([str(e.ROOT/'extensions/rl-lqr-scale/tests'),'-q','--disable-warnings']):raise RuntimeError('Engineering failed')
        e.write(out/'engineering-result.json',dict(passed=True,oracles=[e.oracle_report(e.LQRSpec.from_case(c)) for c in e.CASES]))
    elif op in ('actions','states','confirm'):e.execute(op,out)
    elif op in ('audit','master-audit'):
        from hponas_rl_lqr_scale import audit
        getattr(audit,op.replace('-','_'))(out)
    else:getattr(e,op)(out)
if __name__=='__main__':main()
