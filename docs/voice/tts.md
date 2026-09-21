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
