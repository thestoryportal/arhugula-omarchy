import json
from pathlib import Path
import tempfile
import unittest


class GoalLineageTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)

    def receipt(self,session,tokens,seconds,objective='original scope'):
        path=self.root/(session+str(tokens)+'.json')
        path.write_text(json.dumps({'goal':{'threadId':session,'objective':objective,
            'tokensUsed':tokens,'timeUsedSeconds':seconds,'status':'paused'},'remainingTokens':None}))
        return path

    def test_fresh_native_zero_cannot_erase_lifetime_usage_or_deadline(self):
        from ops.orchestration.goal_lineage import GoalLineage
        ledger=GoalLineage(self.root/'ledger.json')
        ledger.record(self.receipt('old',870069,2834),'2026-10-02T05:06:38Z')
        result=ledger.record(self.receipt('fresh',0,0),'2026-10-02T05:06:38Z')
        self.assertEqual((result['tokens_used'],result['seconds_used']),(870069,2834))
        self.assertEqual(result['deadline'],'2026-10-02T05:06:38Z')
        self.assertEqual(len(result['receipts']),2)

    def test_same_thread_receipts_update_max_without_double_count(self):
        from ops.orchestration.goal_lineage import GoalLineage
        ledger=GoalLineage(self.root/'ledger.json')
        ledger.record(self.receipt('old',10,1),'original')
        result=ledger.record(self.receipt('old',12,2),'original')
        self.assertEqual(result['tokens_used'],12)
        self.assertEqual(len(result['receipts']),2)
        with self.assertRaisesRegex(ValueError,'regressed'):
            ledger.record(self.receipt('old',11,2),'original')

    def test_scope_deadline_and_unbounded_contract_cannot_change(self):
        from ops.orchestration.goal_lineage import GoalLineage
        ledger=GoalLineage(self.root/'ledger.json')
        ledger.record(self.receipt('old',10,1),'original')
        with self.assertRaisesRegex(ValueError,'contract'):
            ledger.record(self.receipt('new',0,0),'extended')
        with self.assertRaisesRegex(ValueError,'contract'):
            ledger.record(self.receipt('other',0,0,'smaller scope'),'original')
