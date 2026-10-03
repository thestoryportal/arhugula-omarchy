# Offline conversation lifecycle

`runtime.voice.conversation.Conversation` runs text-only, multi-turn sessions over
the existing `SessionOwner`. It is an offline integration seam. It does not install
listeners, bind keys, invoke a model, play speech, dispatch commands, write an
archive, or promote memory. The command Coordinator, VoiceRouter, SpeechQueue,
control protocol and shared Profile remain unchanged.

## Bindings and use

Construct `Conversation(owner, snapshot, jobs)` with a shared SessionOwner, a
zero-argument trusted Snapshot supplier, and a zero-argument fresh response-job
factory. The supplier returns a frozen `Snapshot(profile, revision, policy, setup,
context)` from `conversation_records`. The existing Profile is parsed through its
shared codec. All other records are local Python values, not new wire messages.

Policy explicitly names profile ID, policy ID, policy revision, permitted Entry
values (`VOICE`, `PANEL`, `KEYBOARD`), exact exit phrase, exit key and Limits. Missing
policy, disabled profile/voice, mismatched binding, or an exit key in supplied
occupied/reserved sets denies entry. SetupEvidence is caller-attested, revisioned
evidence; it does not inspect actual desktop bindings. There are no default keys.

```python
conversation = Conversation(shared_owner, current_snapshot, fresh_fake_job)
assert conversation.enter(Entry.PANEL)
token = conversation.submit('hello')
response = conversation.poll()  # None while pending, or on cancellation/failure.
notice = conversation.notice    # Inspect code/state to distinguish these cases.
conversation.cancel_turn()      # Keep session/history if lease reacquisition wins.
conversation.end()              # Release ownership and discard transient history.
```

The job contract is `start(request)`, `poll() -> Response | None`, `cancel()`, and
`cleanup_proven`. Cleanup requires the literal boolean `True`; a truthy value,
exception, or missing proof faults admission. The controller calls cancel even
after a successful poll, then rechecks freshness before publishing the response.
Factory/start/poll/cleanup callbacks must return in bounded time. The factory must
return a fresh cleanup-capable job; unknown factory failure faults admission even
if the factory might have allocated nothing. This interface cannot preempt Python
callbacks, verify real resource cleanup, or constrain a malicious injected callable.

## State and input contract

The immutable version-1 notice contains only session/turn identifiers, Display and
Code values. Prompt, response, context, key and exit phrase never enter notices.
Content fields are excluded from record repr; this is not a general logging or
data-access security boundary. `pending` returns a token, and `history` returns
the bounded tuple of completed Exchanges to the trusted caller.

| Input | Result |
| --- | --- |
| `enter(Entry)` | True on admission; falsey plus notice code on denial; BusyError on contention |
| `submit(text)` | New token; None on exact exit or lifecycle failure |
| `poll()` | Current Response after proven cleanup, otherwise None; inspect notice |
| `clarify(Clarification)` | True for an accepted current choice; falsey for stale/foreign choice |
| `exit_key(key)` | True for a recognized configured key; False otherwise |
| `cancel_turn()` | Cancel current work, preserve completed history, attempt a fresh lease |
| `end()` / `handoff()` | Cancel work, release lease, discard transient history |

Submit while another turn is pending raises BusyError, except an exact exit phrase
which can stop processing or clarification. Text is not case-folded, stripped or
substring-matched: `end conversation` and `please end conversation` differ.
Invalid caller types/text raise ValueError. Backend and snapshot errors become
fixed notice codes without exception text. Nested mutating calls from callbacks
raise BusyError; cancellation is accepted and deferred until that callback returns.

Display transitions are inactive → ready → processing/clarifying → ready. Ending
passes through stopping to inactive; unknown cleanup ends in faulted. Notice reads
serialize with transitions and can wait for a bounded callback; reentrant callback
reads can observe stopping. There is no observer callback or background monitor.
Call poll while ready/clarifying to observe external policy/context drift.

## Freshness, interruption and memory

The full snapshot must remain equal through a turn. Revisions must increase on
external changes; an unseen change-and-revert between supplier samples cannot be
detected. Each token binds session, turn, owner generation, profile identity,
profile revision, policy revision and context revision. Foreign, old or replayed
results end the session without publishing. Clarification additionally binds the
exact conflict ID. Cleanup-time drift/cancellation suppresses the result.

Publication rechecks intent and owner acceptance under the cancellation gate after
constructing the Exchange. That check is the local ordering point. A cancellation
that happens after publication does not retroactively revoke a completed exchange.
Snapshot checks are sampled, not atomic transactions with external profile storage.

Context states stay distinct: available has provenance-bearing items; empty has
none; unavailable denies entry; conflicting carries at least two items and a
conflict ID. Conflicting input pauses before job construction. A current
Clarification with `use_current=True` permits that turn with the original context
plus `resolved_conflict`; False rejects the turn. Completed Exchanges retain this
resolution ID. Nothing rewrites context, silently resolves a later conflict, or
promotes the user's speech into persistent memory. The injected responder must
honor the explicit resolution; this module does not interpret memory semantics.

Cancel-turn invalidates the old generation before waiting for callbacks, cleans,
releases and attempts a new conversation lease. It retains session identity,
completed history and turn count only if reacquisition wins. A participating
command/dictation client can win the gap; conversation then becomes inactive with
`conversation.busy`. Late cancellation cannot touch that successor. End/handoff
never reacquire. No callback runs under SessionOwner's lock.

These admission claims cover only clients using the same SessionOwner. Raw
dictation and platform Home/End bindings are not automatically integrated. Cleanup
faults require external reconciliation and cannot be reset on the same owner.

## Bounds and verification

All limits must be explicit positive integers, not booleans. Policy may tighten
these implementation ceilings:

| Limit | Ceiling | Accounting |
| --- | ---: | --- |
| turns | 64 | Includes canceled and rejected turns |
| text_chars | 16,384 | Each prompt/response, counted as Python characters |
| context_chars | 65,536 | Supplied context + completed prompts/responses + current turn |
| context_items | 64 | Supplied provenance-bearing context items |
| polls | 1,024 | Per response job; result on last allowed poll is accepted |

IDs and keys are bounded at 128 characters; IDs use ASCII alphanumeric, `-_.:`.
Setup occupied/reserved sets each hold at most 256 keys. Context records cap each
item at 16,384 characters and total content at 65,536. There is no silent truncation
or eviction. Limit exhaustion ends the session explicitly. Poll counts are not
wall-clock deadlines, and no retention/purge policy is implied by dropping a
transient Python reference.

Verification commands:

```sh
python -m unittest tests.test_conversation_records tests.test_conversation tests.test_voice_session -q
python tests/probe_conversation_mutations.py
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m runtime health
python -m ops.build /path/to/fresh/conversation.pyz
python /path/to/fresh/conversation.pyz health
```

The regression suite includes temporary local Unix-socket tests and needs an
environment that permits their bind operation. Conversation tests use fake jobs
and real SessionOwner admission, including deterministic thread interleavings.
The mutation runner changes module code only in memory and requires assertion
failures in named behavioral tests, with passing unmodified baselines.

Archive `.6br`, pruning `.pi1`, setup `.zcy`, and TTS `.dn6`/`.8l3` remain separate
obligations. Independent actual-code review, required CI, integration and post-main
verification belong to Buford. Offline tests do not release the live feature or
remove the epic's voice-core dependency.
