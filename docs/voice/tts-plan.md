# Offline TTS routing and audio policy implementation plan

> For agentic workers: use superpowers:executing-plans inline after Buford attests
> this written design and plan. Henrietta remains the sole assigned writer.
> Buford routes independent review to the existing team; do not spawn substitutes.
> Steps use checkboxes. No product code is authorized by revision 3.

**Goal:** Exercise policy-bound TTS routing, fake playback and restoration with
bounded resources, cancellation and content-free outcomes.

**Architecture:** New immutable records feed one TtsOutput controller. Existing
GatewayClient and Configuration own synthesis routing/permits, while TTS owns
its fake output handles and borrows the existing conversation generation.

**Tech Stack:** Python 3.11-compatible stdlib, unittest, existing zipapp builder;
no dependencies, device tools or provider installation.

**Spec:** [tts-design.md](tts-design.md), proposed; Buford attestation pending.

## Global constraints

- Base `5a37dca4fb060da692903f03b21a9293e7ef8706`; branch `feat/tts-policy`;
  worktree `/home/robbo/Work/arhugula-omarchy/.worktrees/tts-policy`.
- No actual synthesis/audio/mix/window/network effects, recording, downloads,
  retention or activation authority. All collaborators are fake/offline.
- Reuse GatewayClient and ProviderConfiguration; no copied gateway lifecycle or
  second SessionOwner.
- Existing SpeechQueue/control/Profile/candidate contracts stay unchanged.
- New TTS records/controller/tests/docs only. Report any required shared
  gateway/provider/session change to Buford before making it.
- No ticket dependency removal, closure, push, PR, integration or self-clear.
- Recheck canonical checkpoint task/revision/session and writer before writes.
  A released writer or newer unmatched assignment stops execution immediately.

## Review focus

1. Configuration changes after synthesis cleanup: no player/mix effect (Task 2).
2. Reentrant cancellation followed by late allocation: returned handles still
   retired; no completion success or new TTS synthesis attempt (Task 3).
3. Multibyte text fits character ceiling but exceeds gateway byte budget:
   rejected without provider effect, never truncated (Task 1/2).
4. Playback completes but restoration is false/throws: no PLAYED; fault the
   matching shared lease, never release it clean (Task 3).
5. Old turn/new text and a late cancellation after successor admission: no
   replayed speech and no successor cancellation (Task 2/3).

## Task 1: Policy records and pure admission

**Files:** Create `runtime/voice/tts_records.py`,
`tests/test_tts_records.py`. No shared schema changes.

**Consumes:** Profile codec; ConversationSnapshot/TurnToken/Response; gateway
Request/SpeechInput/request_bytes/parse_request, Active/Disabled configuration.
**Produces:** All records/enums in the spec; two pure boundary functions:

```python
def request_id(token: TurnToken, event: Event) -> str: ...
def admit(utterance: Utterance, snapshot: AudioSnapshot,
          active: Active | Disabled, catalog_version: int) -> Admission: ...
# Admission = Denied(code: Code) | Ready(request: Request, mix: MixIntent)
# MixIntent = Unchanged | Duck | Pause
```

`admit` parses policy/profile/turn/configuration/voice consistency once; runtime
freshness remains TtsOutput's job. It uses the gateway request codec for wire
grammar and limits. Ready contains its parsed Request and selected mix intent.
Disabled configuration returns UNAVAILABLE. Missing policy/profile permission
returns DENIED; mute returns MUTED; missing/Silent event returns SILENT. Owner
acceptance is checked by the controller, not by this pure function.

- [ ] Add record constructor tables: each numeric boundary, bool counts, mutable
  collections, duplicate events/routes, mixed record variants, invalid IDs,
  unknown enum, hidden repr content. Exercise these contract assertions:

```python
with self.assertRaisesRegex(ValueError, 'tts.invalid-record'):
    Duck(True)
with self.assertRaisesRegex(ValueError, 'tts.invalid-record'):
    Limits(16385, 30000, 1, 1)
u = Utterance(token, Event.RESPONSE, 'PRIVATE_SENTINEL')
self.assertNotIn('PRIVATE_SENTINEL', repr(u))
self.assertEqual(request_id(token, Event.RESPONSE),
                 request_id(token, Event.RESPONSE))
self.assertNotEqual(request_id(token, Event.RESPONSE),
                    request_id(token, Event.STATUS))
```

- [ ] Add admission tables using explicit immutable fake policy/configuration:
  primary only; compatible fallback; wrong model/voice/revision; muted/missing
  policy/Silent STATUS; disabled Profile; foreign turn; unavailable context.
  Check 16,384 ASCII chars separately from 16,384 multibyte chars and gateway
  voice+text byte boundaries. Assert no silent truncation.
- [ ] Run `python -B -m unittest tests.test_tts_records -v`; record RED caused
  by missing behavior, not a malformed test fixture.
- [ ] Implement the closed records and the two boundaries. The request-building
  step is explicitly derived from the existing route and wire codec:

```python
raw_request = Request(request_id(utterance.token, utterance.event),
                      active.candidate.host.provider.provider_id,
                      active.candidate.host.provider.model_version,
                      catalog_version, snapshot.policy.limits.synthesis_ms,
                      SpeechInput(utterance.text, rule.voice))
parsed_request = parse_request(request_bytes(raw_request))
# Ready(parsed_request, rule.mix); fixed Denied code on a codec error.
```

- [ ] Repeat focused tests to GREEN, read the diff, then commit only the two
  owned files: `git add runtime/voice/tts_records.py tests/test_tts_records.py`
  followed by `git commit -m 'feat: define offline TTS audio policy records'`.

## Task 2: Gateway composition and fake output lifecycle

**Files:** Create `runtime/voice/tts.py`, `tests/tts_fakes.py`,
`tests/test_tts.py`. Fixtures belong only to the new tests.

**Consumes:** Task 1 values/admission, real GatewayClient and Configuration,
existing SessionOwner. **Produces:** TtsOutput and the playback/mix protocols
from the spec, with PlaybackState PENDING/COMPLETE/FAILED.

```python
TtsOutput(owner, gateway, configuration, catalog_version,
          snapshot, players, mixes)
# players() -> PlaybackJob; mixes() -> MixLease; snapshot() -> AudioSnapshot
start(utterance: Utterance) -> bool
poll() -> Completion | None
cancel() -> None
# properties: notice: Notice; cleanup_proven: bool
```

- [ ] Build explicit fake fixtures using existing gateway/configuration test
  patterns. `Rig` in `tests/tts_fakes.py` owns the following test API: `output`,
  `owner`, `generation`, mutable `snapshot`, `configuration`, deterministic
  `clock`, `events`, `host_requests`, `local_requests`, `player`, `mix`, and
  `utterance(text='answer', event=Event.RESPONSE)`. Set up one real conversation
  generation, real gateway Admission, fake Transport/Local jobs and a real
  Configuration with synthetic evidence/receipts. No installed config is read.
- [ ] Add `Rig.host_audio(pcm)` to enqueue a valid HttpReply via response_bytes,
  `Rig.host_error(code)` to enqueue RemoteError via that same codec,
  `Rig.local_audio(pcm)` for fallback, and `Rig.next_turn()` to advance the
  immutable snapshot token. Fixed constant PCM is `b'\x00\x00' * 240`.
  Record fake boundary calls in `events`; do not assert private controller flags.
  Playback poll defaults to PENDING and has an explicit completion setting.
- [ ] Write this success contract before the controller:

```python
rig = Rig()
rig.host_audio(b'\x00\x00' * 240)
self.assertTrue(rig.output.start(rig.utterance()))
self.assertIsNone(rig.output.poll())  # synthesis -> fake playback
self.assertEqual(rig.output.notice.phase, Phase.PLAYING)
rig.player.state = PlaybackState.COMPLETE
result = rig.output.poll()
self.assertEqual(result.code, Code.PLAYED)
self.assertTrue(rig.output.cleanup_proven)
self.assertTrue(rig.owner.accepts(rig.generation))  # borrowed lease retained
self.assertIsNone(rig.output.poll())
```

- [ ] Add host-transient/VM-success cases with decreasing fake-clock budget,
  preserved logical voice and primary failure provenance; auth, invalid PCM,
  expired health, disabled configuration and denied fallback produce no output.
  Test no fallback after player/mix failure, no second synthesis start, and the
  absence of player/mix calls for muted/silent/unavailable cases.
- [ ] Add current-turn, owner/session, profile/context/audio-policy/configuration
  drift before start, during synthesis and before playback; boundary PCM sizes
  0/1/2/480000/480002 bytes; wrong wire sample format; stale/replayed same event
  with changed text; busy start preserves the original job; snapshot errors.
- [ ] Run `python -B -m unittest tests.test_tts -v`; record RED. Implement the
  state transitions from the spec with one owned call, borrowed generation and
  one terminal result. Route synthesis exclusively through gateway methods.
  Treat invalid callback results as fixed failure, never arbitrary diagnostics.
- [ ] Repeat focused tests to GREEN. Commit only records/controller/test deltas:
  `git add runtime/voice/tts.py tests/tts_fakes.py tests/test_tts.py` then
  `git commit -m 'feat: compose offline TTS routing and fake playback'`.

## Task 3: Cancellation, restoration and fault admission

**Files:** Modify only `runtime/voice/tts.py`, `tests/tts_fakes.py`,
`tests/test_tts.py`; create `tests/test_tts_interleavings.py`.

**Consumes/produces:** Unchanged Task 2 public API. Add test-only callbacks at
factory/apply/start/poll/cancel/restore boundaries and deterministic threading
events; no sleeps used as correctness evidence.

- [ ] Test every acquisition stage: callback cancels then returns a handle;
  callback raises after partial allocation; malformed returned handle; nested
  start/poll; cancellation during synthesis cleanup, playback cleanup, mix
  restoration and completion construction. Cross-thread cancel invalidates
  before waiting; release blocked fake callbacks with Events in test finally.
- [ ] Test cancellation/drift before playback factory, after mix apply and after
  player start; all acquired resources retire once, remaining cleanup is tried
  even after earlier failure, and no successful completion escapes.
- [ ] Pin the gateway-internal sampling limit: mutate audio policy inside a
  transient host-result/cleanup callback, allow the existing gateway to finish
  its synchronous fallback transition, then assert no player/mix calls and
  proven retirement when control returns to TTS. This is not evidence of atomic
  per-attempt policy admission. Stronger synthesis gating needs a separately
  authorized shared binding; do not copy the gateway lifecycle to simulate it.
- [ ] Pin restoration behavior with explicit prior mix state and this fault
  contract (fixture mix.restore_result controls literal proof):

```python
rig = Rig()
rig.host_audio(b'\x00\x00' * 240)
rig.output.start(rig.utterance())
rig.output.poll()
rig.mix.restore_result = False
rig.player.state = PlaybackState.COMPLETE
self.assertEqual(rig.output.poll().code, Code.CLEANUP)
self.assertFalse(rig.output.cleanup_proven)
with self.assertRaises(FaultedError):
    rig.owner.begin('command')
self.assertFalse(rig.output.start(rig.utterance('retry')))
```

- [ ] Test literal False, non-bool truthy return and exceptions independently
  for player cancel and mix restore; gateway cleanup failure suppresses both
  output factories. Repeat cancel cannot reset a fault or duplicate restoration.
  Clean TTS cancellation leaves the borrowed conversation lease accepted.
- [ ] Test a late old-generation failure/cancel against a separately admitted
  successor: the successor stays accepted, the old output stays faulted, and
  no broad owner.cancel or clean release is issued. Document that early shared
  release is an unsupported caller sequence, not an integration success case.
- [ ] Run `python -B -m unittest tests.test_tts_interleavings -v` to RED before
  each corresponding behavior change. Implement deferred cleanup after callback
  unwind and a cancellation/publication gate; recheck generation before success.
  Aggregate cleanup proof without short-circuiting the remaining cleanup calls.
- [ ] Run `python -B -m unittest tests.test_tts_records tests.test_tts
  tests.test_tts_interleavings -v` as one shell line to GREEN. Commit these owned
  files with `git commit -m 'fix: prove TTS cancellation and mix restoration'`.

## Task 4: Adversarial and packaged verification

**Files:** Create `tests/probe_tts_mutations.py`, `tests/tts_package_smoke.py`,
`docs/voice/tts.md`; update this plan's evidence/checklist only while authorized.
**Consumes:** Final public API. **Produces:** Repeatable offline evidence and
limitations for independent actual-code review.

- [ ] Add isolated in-memory mutations with passing original controls and a
  named assertion failure for each: mute bypass; current-turn comparison removal;
  configuration-revision bypass; route/voice mismatch acceptance; changed-content
  replay acceptance; unproven synthesis accepted; playback cleanup ignored;
  restoration ignored; final cancellation gate removed; premature callback
  cleanup; success published before restore. Broken imports/crashes do not count
  as detections. Do not mutate shared modules or files on disk.
- [ ] Run `python -B tests/probe_tts_mutations.py`; require every probe detects
  its change and controls pass. Fix surviving mutants with meaningful contract
  tests and repeat only the affected checks before final regression.
- [ ] Create `tests/tts_package_smoke.py` accepting a pyz path. Remove checkout
  runtime paths before import, assert runtime.__file__ contains that pyz path,
  construct fake collaborators in the smoke script (no tests package imports),
  then exercise primary, fallback, mute and cancellation/restoration through
  the packaged public API. Constant PCM only; no subprocess audio tools.
- [ ] Run the final checks below. Use a fresh mktemp directory; record its actual
  path, exact commands, outputs and tested Git SHA in `docs/voice/tts.md`.

```bash
python -B -W error::ResourceWarning -m unittest discover -s tests -q
python -B tests/probe_tts_mutations.py
git diff --check
python -B -m runtime health
tts_package_dir=$(mktemp -d /tmp/henrietta-tts-package-XXXXXX)
python -B -m ops.build "$tts_package_dir/tts.pyz"
python -B "$tts_package_dir/tts.pyz" health
python -B tests/tts_package_smoke.py "$tts_package_dir/tts.pyz"
```

- [ ] Run `ruff check . --select E4,E7,E9,F` if available. If unavailable, record
  that fact without claiming lint success or installing packages; Buford retains
  the required CI gate. Local Unix-socket fixture tests may need sandbox
  escalation; do not alter tests or production code to hide that environment.
- [ ] Read back docs and audit changed-file scope. Commit owned evidence/tools,
  obtain `git rev-parse HEAD` and `git diff --name-only <base> HEAD`, and send
  Buford the immutable actual-code head, evidence path, limitations and writer
  release. Buford routes review; independent review/CI claims remain separate.
- [ ] Save personal learnings at the authorized transition. Preserve all foreign
  work and the worktree. Do not close the LIT leaf or infer live acceptance.

## Current design-stage evidence

Revision 3 matches this session and authorizes these two documents, the ticket
claim and isolated worktree. Claim succeeded without takeover or dependency
removal. Worktree began clean at the exact assigned base.

`python -B -W error::ResourceWarning -m unittest discover -s tests -q` at that
base: **499 tests passed in 11.755s**, exit 0. Existing local Unix-socket fixtures
ran with approved sandbox escalation. This is baseline evidence, not TTS test
evidence. No TTS implementation, RED/GREEN, mutation or package result is claimed.

## Attestation request and stop

Buford: attest the written design and plan before authorizing implementation.
In particular, attest borrowing the existing generation with matching-lease fault
reporting, the explicit absence of a conversation output coordinator, and the
requirement for compatible logical voices across the whole configured route set.
Also attest the stated gateway-internal sampling limit: stale results are
suppressed before playback, but no atomic per-attempt audio-policy permit is
claimed within the existing gateway. Stronger behavior requires a separate seam.
The proposed execution method is Henrietta inline with existing-team review
routed by Buford. Product implementation remains stopped until matching authority.
