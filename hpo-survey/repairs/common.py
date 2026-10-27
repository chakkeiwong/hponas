"""Standalone companion utilities; no imports of sibling repositories."""
from pathlib import Path
import copy,hashlib,json,sys
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hpo-survey/applications'));sys.path.insert(0,str(ROOT/'hpo-survey/investigations'))
from hponas import Study,StudyDeclaration,EvaluationFold,EvaluationObjective,StudyBudget,SearchSpace,Knob,LocalExecutor
from hponas.types import Config
from hponas.searchers.base import BaseSearcher,SearchSpaceExhaustedError
from hponas.capabilities import SearcherCapabilities,MIXED
from hponas.store import Store
BASE=ROOT/'docs/program/evidence/2026-10-25/app-03'
def save(path,x):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(x,f,indent=2,allow_nan=False)
def read(path):return json.loads(Path(path).read_text())
def binding(path):return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def reject(fn):
    try:fn()
    except (ValueError,AssertionError):return True
    raise AssertionError('Negative control accepted')
class Enumeration(BaseSearcher):
    support=SearcherCapabilities(MIXED)
    def __init__(self,space,grid):super().__init__(space,0);self.grid=copy.deepcopy(grid);self.cursor=0
    def suggest(self):
        if self.cursor>=len(self.grid):raise SearchSpaceExhaustedError('Finite domain consumed')
        c=Config(values=self.grid[self.cursor].copy());self.cursor+=1;return c
    def get_state(self):return {**super().get_state(),'grid':self.grid,'cursor':self.cursor}
    def set_state(self,s):
        if s['grid']!=self.grid or type(s['cursor']) is not int or not 0<=s['cursor']<=len(self.grid):raise ValueError('Changed finite state')
        super().set_state(s);self.cursor=s['cursor']
