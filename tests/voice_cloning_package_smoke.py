"""Build and retain a fresh zipapp, then exercise the packaged cloning API."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = Path(tempfile.mkdtemp(prefix="arhugula-cloning-smoke-", dir="/tmp"))
PYZ = ARTIFACT_DIR / "arhugula.pyz"


def run(args, *, env):
    return subprocess.run(args, cwd=ARTIFACT_DIR, env=env, text=True, capture_output=True, check=True)


def main():
    clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    run([sys.executable, "-m", "ops.build", str(PYZ)], env={**clean_env, "PYTHONPATH": str(ROOT)})
    run([sys.executable, str(PYZ), "health"], env=clean_env)
    probe = """
import runtime
import os
from runtime.voice_candidates import AuthorityEvidence, AuthorityState, CandidateBinding, CandidateRequest, CandidateVersion, Provenance, QualityEvidence, QualityState, VoiceCandidate
from runtime.voice_cloning import CloningEvaluationRequest, EvaluatorFailure, EvaluatorFailureReason, MissingSampleRequirements, QualityDecision, SyntheticDescriptor, evaluate_cloning_request
assert runtime.__file__.startswith(os.environ["ARHUGULA_PYZ"] + os.sep), runtime.__file__
binding = CandidateBinding(CandidateVersion("fixture", 1), Provenance("ref", "digest"))
request = CandidateRequest(binding)
complete = CloningEvaluationRequest(request, SyntheticDescriptor(binding, frozenset({"sample-a"}), frozenset({"sample-a"})))
authority = AuthorityEvidence(binding, AuthorityState.SYNTHETIC_AUTHORIZED)
accepted = QualityDecision(complete, QualityEvidence(binding, QualityState.SYNTHETIC_ACCEPTED))
assert isinstance(evaluate_cloning_request(complete, authority, accepted), VoiceCandidate)
missing = CloningEvaluationRequest(request, SyntheticDescriptor(binding, frozenset({"sample-a"}), frozenset()))
assert evaluate_cloning_request(missing, authority, QualityDecision(missing, QualityEvidence(binding, QualityState.SYNTHETIC_ACCEPTED))) == MissingSampleRequirements(missing, ("sample-a",))
failure = EvaluatorFailure(complete, EvaluatorFailureReason.UNAVAILABLE)
assert evaluate_cloning_request(complete, authority, failure) is failure
"""
    run([sys.executable, "-c", probe], env={**clean_env, "PYTHONPATH": str(PYZ), "ARHUGULA_PYZ": str(PYZ)})
    print(f"package smoke passed; retained artifact: {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()

