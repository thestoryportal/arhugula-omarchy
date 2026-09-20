# Offline conversation lifecycle implementation plan

> For agentic workers: use superpowers:executing-plans inline. Buford routes the
> final immutable-code review to the existing Hannibal session; no new agents.

**Goal:** Safely exercise multi-turn conversation through injected offline inputs.

**Architecture:** Closed immutable records feed a separate Conversation controller.
SessionOwner remains the single admission/cancellation/cleanup authority.

**Tech stack:** Python stdlib, unittest, existing zipapp packaging.

**Spec:** [conversation-design.md](conversation-design.md).

## Global constraints

- Base `91cfb7a5a193ddee21dcd95564fc5b5a3361e985`; dedicated assigned worktree.
- No typing/clipboard/execution/microphone/provider/audio/playback/window effects.
- No shared Profile expansion or command/control/candidate/TTS/gateway/CI edits.
- No dependency removal, ticket closure, publication, integration or live release.
- Explicit immutable policy, setup evidence, bounded context and response jobs.
- Unknown cleanup faults admission; no silent truncation or memory promotion.

## Review focus

1. Cancellation during job construction/start must clean the returned job.
2. Cancellation during cleanup must suppress a successfully computed response.
3. Profile or context drift during a supplier callback must suppress publication.
4. A foreign/replayed clarification must never start a pending response job.
5. A successor command lease must survive a late conversation cancellation.

## Task 1: Closed records and shared admission

Files: create `runtime/voice/conversation_records.py` and
`tests/test_conversation_records.py`; modify `runtime/voice/session.py` and
`tests/test_voice_session.py`.

Consumes: existing frozen Profile; SessionOwner begin/cancel/accepts/release.
Produces: Entry, ContextState, Display, Code enums; Limits, SetupEvidence,
ConversationPolicy, ContextItem, Context, Snapshot, TurnToken, Request, Response,
Exchange, Clarification, Notice. SessionOwner accepts `conversation`.

- [ ] Add constructor rejection tables (bad bool/count/type/enum, excessive
  sizes, illegal context combinations, mutable sets) and collision/binding tests.
- [ ] Add bidirectional admission and cleanup-latch tests:

```python
owner = SessionOwner()
generation = owner.begin('conversation')
with self.assertRaises(BusyError):
    owner.begin('dictation')
owner.cancel(generation=generation)
owner.release(generation, cleaned=False)
with self.assertRaises(FaultedError):
    owner.begin('command')
```

- [ ] Run `python -m unittest discover -s tests -p 'test_conversation_records.py' -v`
  and the session tests. Expected: missing records/conversation mode rejected.
- [ ] Implement frozen records with constructor parsing and exact type bounds;
  add `conversation` to the existing admission mode set.
- [ ] Repeat targeted tests. Expected: all pass. Commit records/admission slice.

## Task 2: Lifecycle and trusted boundaries

Files: create `runtime/voice/conversation.py`, `tests/test_conversation.py`.
Consumes: Task 1 records and SessionOwner.
Produces: Conversation(owner, snapshot, jobs), `enter(channel)`, `submit(text)`,
`poll()`, `clarify(clarification)`, `exit_key(key)`, `cancel_turn()`, `end()`,
`handoff()`, derived `notice`, `history`, `pending`.

- [ ] Add real-owner/fake-job continuity, entry, exit, context, limit and token
  tests. Successful response contract:

```python
conversation.enter(Entry.PANEL)
first = conversation.submit('hello')
job.result = Response(first, 'answer')
self.assertEqual(conversation.poll().text, 'answer')
second = conversation.submit('continue')
self.assertEqual(first.session_id, second.session_id)
self.assertNotEqual(first, second)
self.assertEqual(job.request.history[0].response, 'answer')
```

- [ ] Run `python -m unittest discover -s tests -p 'test_conversation.py' -v`.
  Expected: missing Conversation. Implement the documented state transitions.
- [ ] Add callback/cross-thread cancellation, reentry, cleanup and drift tests
  for all five Review Focus cases before adding their guards. Expected: each
  newly uncovered boundary fails before its production change.
- [ ] Run targeted tests after each change. Expected: all pass. Run full suite
  with `python -W error::ResourceWarning -m unittest discover -s tests -q`.
  Expected: no regressions. Temporary Unix-socket fixtures need sandbox escalation.
- [ ] Commit the controller and behavioral tests.

## Task 3: Adversarial verification and handoff

Files: create `tests/probe_conversation_mutations.py` and
`docs/voice/conversation.md`; update this checklist with measured results.
Consumes: completed Task 1/2 interfaces; produces repeatable review evidence.

- [ ] Add isolated in-memory mutation probes: remove token equality, freshness,
  conflict binding, cleanup fault, exact phrase comparison and generation checks.
  Each mutant must fail a named behavioral test; restored baseline must pass.
- [ ] Run `python tests/probe_conversation_mutations.py`. Expected: all detected.
- [ ] Run full regression, `git diff --check`, `python -m runtime health`,
  `python -m ops.build <fresh-temp-dir>/conversation.pyz`, and packaged health.
  Smoke-import the conversation from the zipapp and exercise a two-turn session.
- [ ] Record exact commands/results, local lint availability and scoped limits.
  Commit and derive `git rev-parse HEAD` and `git diff --name-only <base> HEAD`.
- [ ] Read back docs; send pins/evidence/paths and writer release to Buford for
  Hannibal review. Preserve worktree. Save personal learnings and await transition.
