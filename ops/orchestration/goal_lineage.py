"""Retain actual thread-local goal receipts and derive lifetime accounting."""
import argparse
import hashlib
import json
from pathlib import Path

from .artifacts import file_binding
from .continuation import Lease
from .records import atomic_json


class GoalLineage:
    def __init__(self,path):self.path=Path(path)

    def record(self,receipt,deadline):
        raw=json.loads(Path(receipt).read_text());goal=raw['goal']
        if not goal or raw.get('remainingTokens') is not None or goal.get('tokenBudget') is not None:
            raise ValueError('original unbounded goal contract required')
        contract={'objective':goal['objective'],'deadline':deadline,'token_budget':None}
        usage={k:goal[k] for k in ('tokensUsed','timeUsedSeconds')}
        if any(type(v) is not int or v<0 for v in usage.values()):raise ValueError('invalid actual goal usage')
        bound=file_binding(receipt)
        with Lease(self.path.with_suffix('.lock')):
            state=json.loads(self.path.read_text()) if self.path.exists() else {
                'version':1,**contract,'threads':{},'receipts':[]}
            if any(state[k]!=v for k,v in contract.items()):raise ValueError('goal contract changed')
            for evidence in state['receipts']:
                if file_binding(evidence['path'])!=evidence:raise ValueError('goal receipt changed')
            old=state['threads'].get(goal['threadId'],dict(tokensUsed=0,timeUsedSeconds=0))
            if any(usage[k]<old[k] for k in usage):raise ValueError('actual goal usage regressed')
            state['threads'][goal['threadId']]=usage
            if bound not in state['receipts']:state['receipts'].append(bound)
            state['tokens_used']=sum(v['tokensUsed'] for v in state['threads'].values())
            state['seconds_used']=sum(v['timeUsedSeconds'] for v in state['threads'].values())
            state['objective_sha256']=hashlib.sha256(contract['objective'].encode()).hexdigest()
            atomic_json(self.path,state)
            return state


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--deadline',required=True)
    args=parser.parse_args()
    result=GoalLineage(args.ledger).record(args.receipt,args.deadline)
    print(json.dumps({k:result[k] for k in ('tokens_used','seconds_used','deadline','objective_sha256')}))
