# Synthetic cloning workflow verification

## Verified implementation revision

The implementation and test/probe revision is
`83c0ef89db054805adf530bee0309d7ed5cacbdf`, based on
`5a37dca4fb060da692903f03b21a9293e7ef8706`. This evidence record is added
after that verified revision; the delivery handoff supplies the final branch pin.

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

- `python -m unittest tests.test_voice_cloning -v` passed: 10 tests.
- `python -m unittest tests.test_voice_cloning tests.test_voice_candidates -v`
  passed: 15 tests.
- `python -m tests.probe_voice_cloning_mutations` ran four unmodified passing
  controls, then detected all four in-memory mutations through named assertion
  failures and zero test errors.
- `python -m runtime health` passed in simulation mode with
  `external_execution: false`.
- `python tests/voice_cloning_package_smoke.py` built a fresh pyz, ran health,
  asserted that `runtime.__file__` originated under that pyz, and exercised
  accepted candidate, targeted missing samples, and evaluator failure. It retained
  `/tmp/arhugula-cloning-smoke-m3rs0oqv` for inspection.
- `python -W error::ResourceWarning -m unittest discover -s tests -q` passed:
  509 tests in 13.475 seconds when run outside the sandbox because seven existing
  Unix-socket control tests cannot bind inside it (`control.socket-unavailable`).
- `git diff --check` passed before the evidence commit.

## Limitations

These are local implementation checks, not independent review, CI, integration,
main landing, post-main CI, or a live cloning release. The workflow evaluates only
synthetic metadata supplied by callers. It does not authenticate consent or evaluator
authority, set a quality threshold, retain samples, invoke an evaluator, or authorize
storage, providers, playback, or activation.
