# Offline TTS implementation evidence

Plan: [tts-plan.md](tts-plan.md). Spec: [tts-design.md](tts-design.md).
Buford attested both at `29c843e1fdfb445afdb8440131d315dfc8045bee`, revision 4.
Implementation is in progress; no live release or independent review claimed.

## Execution ledger

- Pre-flight Task 1 -> Task 2: immutable records/admit feed TtsOutput; signatures agree.
- Pre-flight Task 2 -> Task 3: same controller API, adversarial tests extend fake boundaries.
- Pre-flight Task 1/2/3 -> Task 4: probes and packaged smoke use the final public API.
- Ruling: keep the execution ledger here instead of skill-generated scratch
  files/scripts — revision 4 restricts writes to the named TTS files — cost if
  wrong: manual task bookkeeping, without expanding repository scope.
- Task 1 started at `29c843e1fdfb445afdb8440131d315dfc8045bee`.
- Task 1 RED: eight behavioral tests failed on the missing records module.
  GREEN: `python -B -m unittest tests.test_tts_records -q`, eight passed.
- Task 1 complete at `99186e4c957c442e012f1193c5cf25ec246516f6`:
  full regression `python -B -W error::ResourceWarning -m unittest discover -s tests -q`,
  507 tests passed in 14.094s. Paused at this clean commit; revision 6 explicitly
  resumed the remaining native lane through Buford's new session.
- Task 2 started from that records pin; no old work or shared files resumed.
- Task 2 RED: 15 controller tests failed on the missing module. GREEN:
  `python -B -m unittest tests.test_tts -q`, 15 passed. Real gateway/configuration
  objects surround constant-PCM fake effects. Full regression result follows
  in the stable-pin LIT receipt; adversarial Task 3 remains pending.
- Task 2 complete at `b4f223a47131938495b3ea3469832041355377c8`:
  full regression passed 522 tests in 12.571s. Sent to Buford for Hannibal review
  in LIT `cmt-c103f90d-ad84-4ef5-83f1-abe426abe5ba`.
- Task 3: 13 adversarial tests pass, including callback/cross-thread cancellation,
  unknown factories, literal cleanup proofs, final publication cancellation and
  late successor protection. All 36 focused tests pass.
- Ruling: Task 2 already implements the deferred-cleanup behavior exercised by
  Task 3; retain it and commit the extra behavioral coverage without an artificial
  production change — cost if wrong: an untested interleaving, addressed by the
  mutation probes and independent actual-code review. No new RED/GREEN fix is
  claimed for these already-passing characterization tests.
- Task 4 initial probes: 12/12 safeguards detected by assertion failures with
  passing originals, including premature cleanup and success without retirement.
  The probe modifies Python modules in memory, never source files.
