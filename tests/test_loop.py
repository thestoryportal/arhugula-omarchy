import copy
import json
from pathlib import Path
import tempfile
import unittest


class LitBoundary:
    """External LIT seam; all journal/recovery and scheduling code is real."""
    def __init__(self):
        self.data = {'version':2, 'issues':[{'id':f'u{n}', 'status':'open',
            'issue_type':'task', 'labels':[]} for n in range(1,8)], 'relations':[], 'comments':[]}
        self.reads = 0
        self.fail = False

    def read(self, ticket):
        if self.fail:
            raise OSError('LIT read failed')
        self.reads += 1
        return copy.deepcopy(self.data), {'export':'retained-export', 'show':'retained-show'}


class LoopTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.old_transcript=self.root/'old.jsonl'
        self.old_transcript.write_text(json.dumps({'type':'session_meta','payload':{'id':'old'}})+'\n'+
            json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol','effort':'high'}})+'\n'+
            json.dumps({'type':'event_msg','payload':{'type':'task_complete'}})+'\n')
        self.control = self.root/'control.json'
        self.control.write_text(json.dumps({'repair_paused':False,'notification_thread':'old',
            'sessions':[{'role':'buford','session_id':'old','transcript':str(self.old_transcript)},
                        {'role':'runtime','session_id':'protected','transcript':'protected'}]}))
        self.handoff = self.root/'handoff.md'; self.handoff.write_text('full sealed production goal')
        self.lit = LitBoundary()
        from ops.orchestration.loop import Loop
        self.loop = Loop(self.root/'state.json', self.control, self.lit)
        self.loop.initialize('old', 'gpt-6.1-sol', 'high', self.handoff, 'u7')
        self.evidence = self.root/'proof.json'; self.evidence.write_text('{"terminal":"success"}')

    def fresh_transcript(self,name='new'):
        from datetime import datetime,timezone
        transcript=self.root/(name+'.jsonl')
        prompt=(self.root/'package/resume-prompt.txt').read_text()
        transcript.write_text(json.dumps({'type':'session_meta','payload':{'id':name,
            'timestamp':datetime.now(timezone.utc).isoformat()}})+'\n'+
            json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol','effort':'high'}})+'\n'+
            json.dumps({'type':'response_item','payload':{'role':'user','content':[{'type':'input_text','text':prompt}]}})+'\n')
        return transcript

    def close(self, ticket):
        next(x for x in self.lit.data['issues'] if x['id']==ticket)['status']='closed'
        return self.loop.complete(ticket, self.evidence)

    def test_five_closed_tickets_stop_sixth_and_survive_restart(self):
        for n in range(1,6):
            self.loop.begin(f'u{n}')
            self.close(f'u{n}')
        from ops.orchestration.loop import Loop
        restarted = Loop(self.root/'state.json', self.control, self.lit)
        with self.assertRaisesRegex(ValueError,'context-reset-required'):
            restarted.begin('u6')
        self.assertEqual(restarted.status()['epoch_completed'],5)

    def test_duplicate_close_does_not_advance_counter(self):
        self.loop.begin('u1'); self.close('u1'); self.close('u1')
        self.assertEqual(self.loop.status()['epoch_completed'],1)

    def test_each_begin_reads_lit_and_comment_change_invalidates_transition(self):
        first=self.loop.begin('u1')
        self.lit.data['comments'].append({'id':'new-comment','issue_id':'u1','body':'changed scope'})
        with self.assertRaisesRegex(ValueError,'LIT changed'):
            self.loop.check(first['admission'])
        self.loop.begin('u1')
        self.assertEqual(self.lit.reads,3)

    def test_failed_read_never_uses_memory_or_mints_admission(self):
        self.lit.fail=True
        with self.assertRaisesRegex(OSError,'LIT read failed'):
            self.loop.begin('u1')
        self.assertIsNone(self.loop.status()['admission'])

    def test_pause_prevents_workflow_but_explicit_maintenance_can_read(self):
        control=json.loads(self.control.read_text());control['repair_paused']=True
        self.control.write_text(json.dumps(control))
        with self.assertRaisesRegex(ValueError,'production-paused'):
            self.loop.begin('u1')
        self.loop.begin('u1',maintenance=True)
        self.assertTrue(self.loop.status()['production_paused'])

    def test_clear_refuses_owned_writer_and_changed_handoff(self):
        import os
        with self.assertRaisesRegex(ValueError,'owned writer'):
            self.loop.prepare_clear(self.root/'package', [{'pid':os.getpid()}])
        self.handoff.write_text('altered')
        with self.assertRaisesRegex(ValueError,'handoff'):
            self.loop.prepare_clear(self.root/'package', [])

    def test_wrong_model_or_same_identity_cannot_reset_five_ticket_epoch(self):
        self.loop.prepare_clear(self.root/'package', [])
        from ops.orchestration.loop import identity
        transcript=self.root/'new.jsonl'
        transcript.write_text(json.dumps({'type':'session_meta','payload':{'id':'new'}})+'\n'+
            json.dumps({'type':'turn_context','payload':{'model':'gpt-6-astra','effort':'high'}})+'\n')
        with self.assertRaisesRegex(ValueError,'model'):
            self.loop.bootstrap(transcript)
        self.assertEqual(self.loop.status()['epoch'],0)

    def test_fresh_bootstrap_changes_only_buford_and_preserves_pause_and_counts(self):
        self.loop.begin('u1'); self.close('u1'); self.loop.prepare_clear(self.root/'package', [])
        transcript=self.fresh_transcript()
        before=json.loads(self.control.read_text())
        result=self.loop.bootstrap(transcript)
        after=json.loads(self.control.read_text())
        self.assertEqual(after['sessions'][1], before['sessions'][1])
        self.assertEqual(after['repair_paused'],before['repair_paused'])
        self.assertEqual(result['epoch_completed'],0)
        self.assertEqual(len(result['completed']),1)
        self.assertEqual(self.lit.reads,4)

    def test_quarantined_parent_and_dependents_are_excluded(self):
        from ops.orchestration.loop import excluded_scope
        data={'version':2,'issues':[{'id':x} for x in ('parent','bad','child','dependent','okay')],
              'relations':[{'type':'parent-child','src_id':'bad','dst_id':'parent'},
                           {'type':'parent-child','src_id':'child','dst_id':'bad'},
                           {'type':'blocks','src_id':'dependent','dst_id':'bad'}]}
        self.assertEqual(excluded_scope(data,{'bad'}),{'bad','child','dependent'})

    def test_corrupt_journal_is_not_reset_to_empty(self):
        (self.root/'state.json').write_text('{partial')
        with self.assertRaises(ValueError):
            self.loop.begin('u1')

    def test_active_lane_never_becomes_clearable(self):
        self.loop.prepare_clear(self.root/'package', [])
        with self.old_transcript.open('a') as stream:
            stream.write(json.dumps({'type':'event_msg','payload':{'type':'task_started'}})+'\n')
        with self.assertRaisesRegex(ValueError,'idle'):
            self.loop.ready_clear(self.old_transcript)

    def test_crash_after_routing_update_recovers_without_double_epoch(self):
        from unittest.mock import patch
        self.loop.prepare_clear(self.root/'package', [])
        transcript=self.fresh_transcript()
        original=self.loop._save
        def crash_final(state):
            if state['epoch']==1:raise OSError('crash after routing')
            original(state)
        with patch.object(self.loop,'_save',side_effect=crash_final):
            with self.assertRaisesRegex(OSError,'crash after routing'):
                self.loop.bootstrap(transcript)
        self.assertEqual(json.loads(self.control.read_text())['sessions'][0]['session_id'],'new')
        self.assertEqual(self.loop.bootstrap(transcript)['epoch'],1)

    def test_native_close_crash_holds_next_admission_until_completion_reconciled(self):
        self.loop.begin('u1')
        next(x for x in self.lit.data['issues'] if x['id']=='u1')['status']='closed'
        from ops.orchestration.loop import Loop
        restarted=Loop(self.root/'state.json',self.control,self.lit)
        with self.assertRaisesRegex(ValueError,'completion-reconciliation'):
            restarted.begin('u2')
        restarted.complete('u1',self.evidence)
        self.assertEqual(restarted.begin('u2')['epoch_completed'],1)

    def test_preexisting_unrelated_transcript_cannot_bootstrap(self):
        self.loop.prepare_clear(self.root/'package',[])
        transcript=self.root/'unrelated.jsonl'
        transcript.write_text(json.dumps({'type':'session_meta','timestamp':'2020-01-01T00:00:00Z',
            'payload':{'id':'unrelated','timestamp':'2020-01-01T00:00:00Z'}})+'\n'+
            json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol','effort':'high'}})+'\n')
        with self.assertRaisesRegex(ValueError,'fresh handoff'):
            self.loop.bootstrap(transcript)
        self.assertEqual(self.loop.status()['epoch'],0)

    def test_native_injected_agents_prelude_does_not_mask_user_handoff(self):
        self.loop.prepare_clear(self.root/'package',[])
        transcript=self.fresh_transcript()
        lines=transcript.read_text().splitlines()
        lines.insert(1,json.dumps({'type':'response_item','payload':{'role':'user','content':[
            {'type':'input_text','text':'# AGENTS.md instructions for /workspace\n<INSTRUCTIONS>rules</INSTRUCTIONS>'}]}}))
        transcript.write_text('\n'.join(lines)+'\n')
        self.assertEqual(self.loop.bootstrap(transcript)['session_id'],'new')

    def test_new_transcript_without_handoff_token_is_held(self):
        self.loop.prepare_clear(self.root/'package',[])
        transcript=self.fresh_transcript()
        data=transcript.read_text().splitlines();row=json.loads(data[-1]);row['payload']['content'][0]['text']='unrelated task'
        data[-1]=json.dumps(row);transcript.write_text('\n'.join(data)+'\n')
        with self.assertRaisesRegex(ValueError,'fresh handoff'):
            self.loop.bootstrap(transcript)

    def test_arc_ownership_survives_unit_advancing_to_another_arc(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from ops.orchestration.loop import Loop
        product=self.root/'product';(product/'tools').mkdir(parents=True);(product/'.harness').mkdir()
        for path in ['tools/review_loop_gate.py','.harness/merge-gate-log.jsonl']:(product/path).write_text('')
        gate=SimpleNamespace(FULL_DIFF_REF='origin/main',
            rw=SimpleNamespace(code_binding=lambda *x:{'head_sha':'head','base_sha':'base','diff_digest':'digest'}),
            fr=SimpleNamespace(read_rows=lambda *x:[]),completing_run=lambda *x:None)
        result={'decision':'review_required','completed_passes':4,'observed':[],
            'admit_review':True,'next_pass':'3','blocking_findings':[],'followups':[]}
        with patch('ops.orchestration.loop.load_gate',return_value=gate),patch('ops.orchestration.loop.evaluate',return_value=result.copy()),patch.object(self.lit,'command',return_value=('', 'receipt'),create=True):
            self.loop.review('u1',product,'arc-A',unit='stable')
            self.loop.review('u1',product,'arc-B',unit='stable')
            with self.assertRaisesRegex(ValueError,'renamed'):
                self.loop.review('u1',product,'arc-A',unit='renamed')

    def test_quarantine_native_backlog_skips_fresh_foreign_claim(self):
        from unittest.mock import patch
        from ops.orchestration.loop import NativeLit
        native=NativeLit(self.root,self.root/'artifacts')
        data={'version':2,'issues':[{'id':x,'status':'open'} for x in ('bad','foreign','ready')],'relations':[]}
        outputs=[('bad open task quarantined','next-receipt'),
                 (' 1. bad open -\n unclaimed\n 2. foreign open -\n claimed elsewhere (fresh): /other\n 3. ready open -\n unclaimed\n','backlog-receipt')]
        with patch.object(native,'command',side_effect=outputs):
            self.assertEqual(native.next(data,{'bad'}),('ready','backlog-receipt'))
