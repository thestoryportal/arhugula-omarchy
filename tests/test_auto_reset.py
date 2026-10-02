import json
from pathlib import Path
import unittest
import test_loop


class WindowSeam:
    def __init__(self):self.name='old';self.lines=[];self.pending=None
    def check(self):return {'title':self.name}
    def title(self):return self.name
    def type(self,text):self.pending=text;self.lines.append(text)
    def submit(self):
        if self.pending.startswith('/clear '):self.name=self.pending[7:]


class AutoResetTests(unittest.TestCase):
    def setUp(self):
        fixture=test_loop.LoopTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.root=fixture.root;self.loop=fixture.loop
        from ops.orchestration.artifacts import file_binding
        authority=self.root/'authority';authority.write_text('user requires automatic clear and continuation')
        instructions=self.root/'continuation';instructions.write_text('Continue acceptance then authorized production without HIL.')
        goal=self.root/'goal.json';goal.write_text(json.dumps({'goal':{'threadId':'old','objective':'full scope',
            'tokensUsed':100,'timeUsedSeconds':10,'status':'paused'},'remainingTokens':None}))
        self.release=self.root/'release.json'
        self.release.write_text(json.dumps({'session_id':'old','epoch':0,'owned_processes':[],
            'goal_receipt':str(goal),'completed':[]}))
        self.config={'authority':file_binding(authority),'continuation':file_binding(instructions),
            'release':str(self.release),'packages':str(self.root/'packages'),
            'goal_ledger':str(self.root/'lineage.json'),'deadline':'original',
            'receipt_directory':str(self.root/'receipts'),'sessions':str(self.root),
            'source_acceptance':[file_binding(authority)]}
        self.window=WindowSeam();self.clock=100

    def controller(self):
        from ops.orchestration.auto_reset import AutoReset
        return AutoReset(self.loop,self.root/'supervisor.json',self.config,self.window,lambda:self.clock)

    def hold(self):
        self.loop.prepare_clear(self.root/'old-package',[])

    def fresh(self):
        state=self.loop.status();package=Path(state['reset']['directory'])
        self.f.root.joinpath('package').mkdir(exist_ok=True)
        self.f.root.joinpath('package/resume-prompt.txt').write_text((package/'resume-prompt.txt').read_text())
        return self.f.fresh_transcript()

    def test_fifth_close_automatically_prepares_clears_and_submits_full_prompt(self):
        for n in range(1,6):self.loop.begin(f'u{n}');self.f.close(f'u{n}')
        release=json.loads(self.release.read_text());release['completed']=sorted(self.loop.status()['completed'])
        self.release.write_text(json.dumps(release))
        controller=self.controller()
        for _ in range(4):controller.step()
        self.assertEqual(len(self.window.lines),2)
        self.assertTrue(self.window.lines[0].startswith('/clear Buford-auto-'))
        self.assertIn('BUFORD_CONTEXT_HANDOFF',self.window.lines[1])
        self.assertIn('without HIL',self.window.lines[1])
        controller.step(self.fresh())
        self.assertEqual(self.loop.status()['epoch'],1)
        self.assertEqual(len(self.loop.status()['completed']),5)
        self.assertEqual(controller.status()['phase'],'verified')

    def test_active_parent_is_held_without_window_input(self):
        self.hold()
        with self.f.old_transcript.open('a') as stream:
            stream.write(json.dumps({'type':'event_msg','payload':{'type':'task_started'}})+'\n')
        controller=self.controller();controller.step()
        self.assertEqual(self.window.lines,[])
        self.assertEqual(controller.status()['phase'],'waiting_idle')

    def test_late_user_message_invalidates_prepared_reset(self):
        self.hold();controller=self.controller();controller.step()
        with self.f.old_transcript.open('a') as stream:
            stream.write(json.dumps({'type':'response_item','payload':{'role':'user','content':[{'text':'pause now'}]}})+'\n')
        with self.assertRaisesRegex(ValueError,'user input changed'):controller.step()
        self.assertEqual(self.window.lines,[])

    def test_changed_authority_or_control_refuses_delivery(self):
        self.hold();controller=self.controller();controller.step()
        self.f.control.write_text(self.f.control.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'routing'):controller.step()
        self.assertEqual(self.window.lines,[])

    def test_uncertain_native_delivery_is_never_blindly_replayed(self):
        self.hold();controller=self.controller();controller.step()
        def crash(text):raise OSError('transport uncertain')
        self.window.type=crash
        with self.assertRaisesRegex(OSError,'uncertain'):controller.step()
        recovered=self.controller()
        with self.assertRaisesRegex(ValueError,'uncertain'):recovered.step()
        self.assertEqual(self.loop.status()['epoch'],0)

    def test_wrong_fresh_model_keeps_production_held(self):
        self.hold();controller=self.controller()
        for _ in range(4):controller.step()
        fresh=self.fresh();fresh.write_text(fresh.read_text().replace('gpt-6.1-sol','gpt-6-astra'))
        with self.assertRaisesRegex(ValueError,'model'):controller.step(fresh)
        self.assertEqual(self.loop.status()['epoch'],0)

    def test_reset_deadline_is_clear_to_bootstrap_not_active_turn_wait(self):
        self.hold();controller=self.controller();controller.step()
        controller.step();self.clock+=121
        with self.assertRaisesRegex(ValueError,'deadline'):controller.step()

    def test_receipt_publication_crash_recovers_without_second_epoch_or_prompt(self):
        from unittest.mock import patch
        self.hold();controller=self.controller()
        for _ in range(4):controller.step()
        fresh=self.fresh()
        with patch.object(controller,'publish',side_effect=OSError('receipt disk failure')):
            with self.assertRaisesRegex(OSError,'disk failure'):controller.step(fresh)
        self.assertEqual(self.loop.status()['epoch'],1)
        recovered=self.controller();recovered.step(fresh)
        self.assertEqual(self.loop.status()['epoch'],1)
        self.assertEqual(len(self.window.lines),2)
        self.assertEqual(recovered.status()['phase'],'verified')

    def test_stale_release_waits_for_current_fifth_boundary_instead_of_exiting(self):
        for n in range(1,6):self.loop.begin(f'u{n}');self.f.close(f'u{n}')
        controller=self.controller();controller.step()
        self.assertEqual(controller.status()['phase'],'waiting_release')
        self.assertEqual(self.window.lines,[])
        release=json.loads(self.release.read_text());release['completed']=sorted(self.loop.status()['completed'])
        self.release.write_text(json.dumps(release));controller.step()
        self.assertEqual(controller.status()['phase'],'waiting_idle')

    def test_headroom_hold_is_persisted_and_prepared_without_five_closes(self):
        with self.assertRaisesRegex(ValueError,'context-reset-required'):self.loop.begin('u1',headroom=False)
        controller=self.controller();controller.step()
        self.assertEqual(controller.status()['phase'],'waiting_idle')

    def test_unpublished_native_receipt_holds_new_epoch_admission(self):
        from unittest.mock import patch
        self.hold();controller=self.controller()
        for _ in range(4):controller.step()
        with patch.object(controller,'publish',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):controller.step(self.fresh())
        with self.assertRaisesRegex(ValueError,'native reset receipt'):
            self.loop.begin('u1')
