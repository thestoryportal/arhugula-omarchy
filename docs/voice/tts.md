# Offline TTS implementation evidence

Plan: [tts-plan.md](tts-plan.md). Spec: [tts-design.md](tts-design.md).
Buford attested both at `29c843e1fdfb445afdb8440131d315dfc8045bee`, revision 4,
and re-attested them in revision 6. The implementation uses only fake/offline
effects; local verification is separate from independent review and release.

## Interface and binding

`runtime.voice.tts.TtsOutput` receives the existing SessionOwner, a dedicated
GatewayClient and its Configuration, catalog revision, AudioSnapshot supplier,
and inert player/mix factories. No default backend, provider mapping, activation,
device selection, daemon or output binding is installed.

Supply `Utterance(response.token, Event.RESPONSE, response.text)` from a trusted
response source. `start` reports admission, `poll` advances work and returns one
content-free Completion, and `cancel` invalidates pending output. Consume any
terminal result before starting another utterance. `notice` and `cleanup_proven`
do not call collaborators. STATUS is silent without an explicit Spoken rule.

AudioPolicy binds profile/policy identity, revisions, event rules, logical voices
and bounded work. The whole configured host/fallback route set must support the
selected logical voice. Wire parsing, health, budget permits, replay and transient
fallback remain with the existing gateway/configuration owners. TTS never retries
after output begins or treats playback failure as a synthesis fallback trigger.

Mix leases restore only their owned changes. Completion requires synthesis
cleanup, player quiescence and mix restoration; truthy values are insufficient.
Unknown factory outcomes or cleanup fault the local controller and the matching
borrowed shared generation. Clean TTS retirement leaves the conversation lease
owned. A late failure cannot fault/cancel a successor's generation.

## Scope limits

The trusted caller must publish the latest output-eligible turn after conversation
response delivery, since Conversation.pending is then None. No conversation/TTS
coordinator is installed: the caller must cancel and prove output cleanup before
new capture, handoff or releasing shared ownership. Direct Conversation.end with
an outstanding output borrower is unsupported.

The outer snapshot check cannot atomically gate gateway-internal fallback.
An internal fallback can start before an audio-policy change is resampled; its
result is discarded and cleaned before player/mix effects. A dedicated regression
pins this accepted offline limit. Real synthesis/output would need separately
authorized per-attempt and device bindings. Revision sampling also cannot detect
unseen change-and-revert; callbacks must be bounded, and foreground polling is
required. Poll counts do not impose a wall-time deadline on arbitrary Python.

Text/PCM are transient and excluded from status/errors/repr. Retirement drops
controller references; this is neither secure erasure nor an archive policy.
P4/.8l3 provider and real-playback decisions, P8 human acceptance, voice cloning,
retention and full voice-stack release remain external. No live effects were run.

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
- Hannibal records finding, relayed and independently reproduced by Buford in
  LIT `cmt-34ab31d4-3607-4f39-a14b-0f3a102bda9c`: public Denied/Ready constructors
  admitted malformed direct values. Two new regression tests reproduced it
  before correction. Denied now requires Code; Ready now owns canonical gateway
  parsing plus the speech-payload/mix type constraints. Admission delegates to
  that constructor instead of keeping a second wire parsing site.
  GREEN: 10 records tests, 38 focused tests, full 537 tests in 12.390s; 12/12
  mutations still detected. This is implementer verification, not review clearance.

## Final local verification

Runtime/controller source is pinned at `b92fdd0ca2145a4579d3854aab2eeca2c0647cd0`.
The final handoff commit adds verification tools and documentation; its immutable
SHA is in the LIT writer-release receipt to avoid a self-referential commit hash.

| Command | Observed result |
| --- | --- |
| `python -B -m unittest tests.test_tts_records tests.test_tts tests.test_tts_interleavings -q` | 38 tests passed |
| `python -B -W error::ResourceWarning -m unittest discover -s tests -q` | 537 tests passed in 12.226s, exit 0 |
| `python -B tests/probe_tts_mutations.py` | 12/12 mutations detected by assertion failures; original controls passed |
| `git diff --check` | Passed |
| `python -B -m runtime health` | Simulation, state ok, external_execution false |
| `python -B -m ops.build /tmp/henrietta-tts-package-aQBitr/tts.pyz` | Fresh stdlib zipapp built |
| `python -B /tmp/henrietta-tts-package-aQBitr/tts.pyz health` | Simulation, state ok, external_execution false |
| `python -B tests/tts_package_smoke.py /tmp/henrietta-tts-package-aQBitr/tts.pyz` | Packaged primary/fallback/mute/cancel passed; packaged imports confirmed |

The full suite used approved sandbox escalation for existing local Unix-socket
fixtures. No microphone, output device, real provider, window or network synthesis
was exercised. Ruff executable and Python module are absent locally; lint success
is not claimed. Buford retains the required CI lint/test/package gates.

Independent status at handoff preparation: Buford relayed Hannibal's scoped Ready
controller/interleaving verdict through `55c9546` in LIT
`cmt-080e52e1-e165-42a4-a08c-ffda834b9686`: 28 isolated tests passed and no material
new defect found. Hannibal's initial records finding is corrected with RED/GREEN
evidence; correction clearance and final tool/docs review remain pending. These
verdicts remain separate from implementer evidence. Integration, main landing,
post-main verification and LIT closure remain Buford-owned.
