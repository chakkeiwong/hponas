from pathlib import Path
import sys
from diagnose import main,ROOT,BASE
op,out=sys.argv[1],Path(sys.argv[2])
if op!='diagnose' or not out.resolve().is_relative_to(BASE) or not out.is_dir():raise ValueError('Fixed diagnostic output required')
main(out)
