"""Offline TTS mutations in memory; every detection must be an assertion failure."""
import importlib
import io
from pathlib import Path
import sys
import unittest


MUTATIONS = (
    ('mute', 'tts_records', (('if snapshot.muted:', 'if False:', 1),),
     'tests.test_tts_records.TtsRecordsTests.test_muted_missing_silent_and_disabled_are_distinct_denials'),
    ('turn', 'tts_records', (('t != snapshot.current_turn', 'False', 1),),
     'tests.test_tts_records.TtsRecordsTests.test_foreign_turn_and_revision_mismatch_deny'),
    ('configuration', 'tts_records', (('p.configuration_revision != active.revision', 'False', 1),),
     'tests.test_tts_records.TtsRecordsTests.test_foreign_turn_and_revision_mismatch_deny'),
    ('voice', 'tts_records', (('if any(RouteVoice(', 'if False and any(RouteVoice(', 1),),
     'tests.test_tts_records.TtsRecordsTests.test_fallback_requires_compatible_voice_on_every_route'),
    ('replay', 'tts_records', (('Request(request_id(t, utterance.event),',
       'Request(request_id(t, utterance.event) + hashlib.sha256(utterance.text.encode()).hexdigest()[:8],', 1),),
     'tests.test_tts.TtsTests.test_replayed_turn_with_changed_text_cannot_play_again'),
    ('synthesis-proof', 'tts', (('self._gateway.cleanup_proven is True', 'True', 2),),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_all_three_cleanup_proofs_require_literal_true'),
    ('playback-proof', 'tts', (('proven = getattr(handle, method)() is True',
       "proven = (getattr(handle, method)() is True) or method == 'cancel'", 1),),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_all_three_cleanup_proofs_require_literal_true'),
    ('restoration-proof', 'tts', (('proven = getattr(handle, method)() is True',
       "proven = (getattr(handle, method)() is True) or method == 'restore'", 1),),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_all_three_cleanup_proofs_require_literal_true'),
    ('publication-gate', 'tts', (('if clean and call.epoch != self._epoch:', 'if False:', 1),),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_completion_construction_cancel_wins_before_publication'),
    ('premature-cleanup', 'tts', (
        ('if self._call is not None and not self._busy:', 'if self._call is not None:', 1),
        ('self._run(lambda: self._retire(Code.CANCELED))', 'self._retire(Code.CANCELED)', 1)),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_late_allocation_after_reentrant_cancel_is_still_cleaned'),
    ('success-without-retirement', 'tts', (('clean = self._cleanup(call)',
        'clean = True if code in (Code.PLAYED, Code.DEGRADED) else self._cleanup(call)', 1),),
     'tests.test_tts.TtsTests.test_primary_plays_once_after_synthesis_cleanup_and_keeps_lease'),
    ('unknown-factory', 'tts', (('call.unknown = True', 'call.unknown = False', 2),),
     'tests.test_tts_interleavings.TtsInterleavingTests.test_unknown_factory_outcome_faults_shared_admission'),
)


def fresh():
    prefixes = ('runtime.voice.tts', 'tests.test_tts', 'tests.tts_fakes')
    for name in tuple(sys.modules):
        if name.startswith(prefixes):
            parent, _, child = name.rpartition('.')
            package = sys.modules.get(parent)
            if package is not None and hasattr(package, child):
                delattr(package, child)
            del sys.modules[name]


def run(name):
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if result.testsRun != 1 or result.errors:
        raise RuntimeError(output.getvalue())
    return result, output.getvalue()


def main():
    for label, module_name, changes, test in MUTATIONS:
        fresh()
        baseline, output = run(test)
        if not baseline.wasSuccessful():
            raise RuntimeError('baseline failed: ' + output)
        fresh()
        module = importlib.import_module('runtime.voice.' + module_name)
        source = Path(module.__file__).read_text()
        for before, after, count in changes:
            if source.count(before) != count:
                raise RuntimeError('mutation anchor changed: ' + label)
            source = source.replace(before, after)
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        result, output = run(test)
        if result.wasSuccessful():
            raise RuntimeError('SURVIVED: ' + label)
        print('DETECTED:', label, '|', test)
    fresh()
    print(f'{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected; controls pass; no source files changed')


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
