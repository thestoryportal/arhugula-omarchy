"""Run offline conversation negative probes entirely in memory; no source writes."""
import importlib
import io
from pathlib import Path
import sys
import unittest


MUTATIONS = (
    ('result.token != self.pending', 'False', 1,
     'test_stale_foreign_replayed_response_never_enters_history'),
    ('current != self._snapshot', 'False', 1,
     'test_profile_context_setup_or_policy_drift_ends_without_response'),
    ('self._job.cleanup_proven is True', 'True', 1,
     'test_failed_or_unknown_cleanup_faults_all_admission'),
    ('if value == policy.exit_phrase:', 'if policy.exit_phrase in value:', 1,
     'test_exact_spoken_exit_and_configured_key'),
    ('clarification.token != self.pending', 'False', 1,
     'test_conflict_requires_exact_current_clarification_and_keeps_provenance'),
    ('clarification.conflict_id != self._request.context.conflict_id', 'False', 1,
     'test_foreign_conflict_rejection_cannot_resolve_current_turn'),
    ('not self.owner.accepts(self._lease)', 'False', 2,
     'test_external_owner_cancel_ends_conversation_without_reacquisition'),
    ('raise _Stop(Code.CLEANUP)\n            self._check()',
     'raise _Stop(Code.CLEANUP)\n            pass', 1,
     'test_drift_during_job_start_poll_and_cleanup_suppresses_results'),
    ('self._polls >= limits.polls', 'False', 1,
     'test_turn_text_context_and_poll_limits_fail_explicitly'),
    ('policy.exit_key in snapshot.setup.occupied | snapshot.setup.reserved', 'False', 1,
     'test_disabled_missing_mismatched_policy_and_collision_deny_entry'),
    ('self._unknown_job = True\n            self._job = self._jobs()',
     'self._unknown_job = False\n            self._job = self._jobs()', 1,
     'test_unknown_factory_outcome_faults_admission'),
)


def fresh():
    for name in tuple(sys.modules):
        if name.startswith(('runtime.voice.conversation', 'tests.test_conversation')):
            parent, _, child = name.rpartition('.')
            package = sys.modules.get(parent)
            if package is not None and hasattr(package, child):
                delattr(package, child)
            del sys.modules[name]
    return importlib.import_module('runtime.voice.conversation')


def run(name):
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        'tests.test_conversation.ConversationTests.' + name)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if result.testsRun != 1 or result.errors:
        raise RuntimeError(output.getvalue())
    return result, output.getvalue()


def main():
    for before, after, count, name in MUTATIONS:
        fresh()
        result, output = run(name)
        if not result.wasSuccessful():
            raise RuntimeError('baseline failed: ' + output)
        module = fresh()
        source = Path(module.__file__).read_text()
        if source.count(before) != count:
            raise RuntimeError('mutation anchor changed: ' + before)
        exec(compile(source.replace(before, after), module.__file__, 'exec'), module.__dict__)
        result, output = run(name)
        if result.wasSuccessful():
            raise RuntimeError('SURVIVED: ' + before)
        print('DETECTED:', before, '->', after, '|', name)
    fresh()
    print(f'{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected; no files changed')


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
