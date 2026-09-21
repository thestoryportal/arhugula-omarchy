# Synthetic cloning workflow verification

## Verified implementation revision

The final runtime, test, and verification-tool revision is
`48e881fd29d765eb3eee4aaf020760aca1feb55e`, based on
`5a37dca4fb060da692903f03b21a9293e7ef8706`. The implementer released
`0e28cde864052872b11aeaf809e383e1cd06a74c`, which adds only the routing-review
evidence supplement to that tested revision. This document distinguishes the
implementer's checks from Buford's integration checks. Use the LIT landing receipt
for the verified final merge SHA and CI runs.

## Scope audit

The implementation changes only these owned paths:

- `runtime/voice_cloning.py`
- `tests/test_voice_cloning.py`
- `tests/probe_voice_cloning_mutations.py`
- `tests/voice_cloning_package_smoke.py`
- `docs/voice/cloning-workflow-design.md`
- `docs/voice/cloning-workflow-plan.md`
- this evidence document

No existing candidate contract, product provider, storage, recording, audio, live
effect, consent policy, threshold, or activation path changed.

## Local verification

- `python -m unittest tests.test_voice_cloning -v` passed: 11 tests after the
  final routing regression. Hannibal independently reproduced all 11 at the
  final runtime/test revision.
- `python -m tests.probe_voice_cloning_mutations` ran four unmodified passing
  controls, then detected all four in-memory mutations through named assertion
  failures and zero test errors.
- `python -m runtime health` passed in simulation mode with
  `external_execution: false`.
- `python tests/voice_cloning_package_smoke.py` built a fresh pyz, ran health,
  asserted that `runtime.__file__` originated under that pyz, and exercised
  accepted candidate, targeted missing samples, and evaluator failure. The initial
  implementation artifact was `/tmp/arhugula-cloning-smoke-m3rs0oqv`; the final
  combined artifact is identified under integration checks below.
- `python -W error::ResourceWarning -m unittest discover -s tests -q` passed:
  510 tests after the final routing regression, as reported in Munson's writer
  release `cmt-96dc013d-ee97-492e-a864-b5b4585b2e3c`. This ran outside the sandbox
  because seven existing Unix-socket control tests cannot bind inside it
  (`control.socket-unavailable`).
- `git diff --check` passed before the evidence commit.

## Limitations

Local implementation checks are distinct from the attributed independent review
and integration checks below. CI, main landing, and post-main CI need their own
LIT landing receipt; this document does not claim a live cloning release.
The workflow evaluates only synthetic metadata supplied by callers. It does not authenticate consent or evaluator
authority, set a quality threshold, retain samples, invoke an evaluator, or authorize
storage, providers, playback, or activation.

## Constructor-correction supplement

Buford independently reproduced that `MissingSampleRequirements` accepted
`(unittest.mock.ANY,)` because tuple equality alone did not prove each element was a
sample-ID string. The direct constructor regression failed before the correction and
passes at `e9cbb81dadc2d7733df6843f94cb73cd795a4b7a`, which rejects every non-string or
empty tuple element before comparing the canonical derived tuple. The same correction
removed the unused production `QualityState` import; the mutation probe now supplies
that mutation-only symbol in its own namespace. Focused workflow tests, 4/4 assertion
mutation probes, fresh-package smoke, and the external 509-test ResourceWarning-error
suite passed after the correction.

## Routing-review supplement

Hannibal's routing review, relayed by Buford, requested coverage for the remaining
early-validation ordering: contradictory authority must raise before an otherwise
matching evaluator failure can be returned. The expected-GREEN regression at
`48e881fd29d765eb3eee4aaf020760aca1feb55e` asserts that ordering without changing
production code. The focused workflow suite passed 11 tests, the four assertion
mutation probes passed, fresh-package smoke passed, and the external
ResourceWarning-error full suite passed 510 tests after this addition.

## Independent review and integration checks

Hannibal independently reviewed the values, routing, constructor correction,
early-return regressions, and verification tools through the final runtime/test
revision above. His final checks passed 11 focused tests, all four assertion-based
mutation probes, and fresh packaged API smoke. His evidence-summary finding is
addressed by this documentation-only consolidation; its review disposition belongs
in the LIT record, not an assertion by its author.

Buford prepared the candidate on an integration branch based on main
`72c390aea8b41d5ead6ab6f753cf3f2420fd4d4a`, which already contains offline TTS.
The combined executable tree at `90fb1311ada0528cfd164e342d928585a462d635`
passed 548 tests in 12.308 seconds with ResourceWarning treated as an error,
four cloning and twelve TTS assertion-based mutation probes, and source health.
One fresh zipapp at `/tmp/arhugula-cloning-smoke-d13hrhh5/arhugula.pyz` passed
the cloning API scenarios and TTS primary, fallback, mute, and cancel scenarios.
Imported runtime paths were checked against that archive.

Integration commit `1e096c9847dbbaecd52645b6a61cf6287618550d` and this
consolidation change only documentation relative to that tested executable tree.
Buford verified runtime, tests, build tooling, and CI configuration remain
byte-for-byte unchanged. Required PR and post-main CI remain separate gates.
