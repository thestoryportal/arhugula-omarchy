"""Offline in-memory behavioral mutation probes for the cloning workflow."""
import importlib
import io
from pathlib import Path
import sys
import unittest


MUTATIONS = (
    ("if authority is not None:", "if False:", 1,
     "test_contradictory_authority_binding_rejected_before_missing_sample_outcome"),
    ("if missing:", "if False:", 1,
     "test_missing_required_sample_is_not_a_candidate"),
    ("return evaluator_result", "return represent_candidate(request.request, authority, None)", 1,
     "test_evaluator_failure_is_not_rejected_quality"),
    ("quality = None if evaluator_result is None else evaluator_result.evidence",
     "quality = QualityEvidence(request.request.binding, QualityState.SYNTHETIC_ACCEPTED) if evaluator_result is None else evaluator_result.evidence", 1,
     "test_missing_evaluator_result_preserves_quality_missing"),
)


def fresh():
    for name in tuple(sys.modules):
        if name.startswith(("runtime.voice_cloning", "tests.test_voice_cloning")):
            del sys.modules[name]
    return importlib.import_module("runtime.voice_cloning")


def run(name):
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_voice_cloning.VoiceCloningTests." + name)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if result.testsRun != 1:
        raise RuntimeError(output.getvalue())
    return result, output.getvalue()


def main():
    for before, after, count, name in MUTATIONS:
        fresh()
        control, output = run(name)
        if not control.wasSuccessful():
            raise RuntimeError("control failed: " + output)
        module = fresh()
        source = Path(module.__file__).read_text()
        if source.count(before) != count:
            raise RuntimeError("mutation anchor changed: " + before)
        exec(compile(source.replace(before, after, 1), module.__file__, "exec"), module.__dict__)
        mutated, output = run(name)
        if mutated.errors or not mutated.failures:
            raise RuntimeError("mutation did not produce an assertion failure: " + output)
        print("DETECTED:", name)
    fresh()
    print(f"{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected; no files changed")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
