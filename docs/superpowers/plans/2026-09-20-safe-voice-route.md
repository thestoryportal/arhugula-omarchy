# Safe Voice Route Implementation Plan

> Execute inline with superpowers:executing-plans, then one Astra/high whole-branch
> review. User delegates routine implementation choices and authorized exactly
> one Omarchy-menu smoke after offline verification.

Goal: route one action through VM validation with clarification, correction
preview, trusted confirmation and durable observations, never generated shell.
Spec: approved workspace design, B.3–B.5, voice-adapter-contracts design.
Stack: Python >=3.11 standard library, existing contracts/core/SQLite journal.

## Global constraints

No microphone, live typing/clipboard, audio playback, keybindings, service/config
changes, provider downloads or network. Only live action is one explicit
`omarchy menu summon root` smoke, after tests/review. No automatic retry.

## Decisions and seams

Keep authorization in ControlPlane, not the semantic router. Add VM-only
`request_confirmation(command, context_key)` and
`confirm(token, channel, context_key, approved=True)`. A random single-use token
stores an immutable command, caller-context epoch and 30-second expiry. Unknown,
replayed, expired or context-mismatched tokens cannot execute. Confirm rechecks
current policy/catalog; callers cannot set a confirmed field in Command.
Only panel/keyboard/voice trusted adapters call confirm. These Python methods
are not exposed as model tools or network endpoints.

Add a new per-kind v1 Interaction record for non-execution observations, with
event/interaction/correlation IDs, timestamp, context, phase and safe details.
Journal accepts both Event and Interaction; dispatch replay suppression uses
execution Events only. This avoids calling previews successful executions or
poisoning the command-ID replay guard. Unknown kinds remain rejected. Store no
transcript, audio, confirmation token or raw provider exception in the journal.

VoiceRouter binds trusted Action definitions (capability, fixed arguments,
aliases and display label), current VoiceState (context, context key, activation
token, mute/mode), an optional proposal function and a speech-response seam.
Normalize Unicode/case/punctuation/spacing. Exact aliases are deterministic;
otherwise a bounded provider proposal or lexical fallback ranks known IDs.
Confidence below 0.85 or top-two gap below 0.15 clarifies; no action executes.
Provider proposals are closed-shape data, not authorization. Malformed output
clarifies. Each voice turn requires a new activation token. Corrections always
preview; risk-confirm actions preview; safe exact actions still pass VM policy.
Muted/wrong-mode/stale-context turns never execute or speak. Voice confirmations
require a new activation; panel/keyboard are separate trusted calls. No live TTS.

OmarchyMenuExecutor accepts only menu.open with fixed name=main, uses argv
without a shell and only `omarchy menu summon root`. Missing executable is failed;
timeouts/nonzero/unknown effects are uncertain. The smoke CLI defaults to fake
execution; live requires an explicit flag and persistent journal, using one
stable smoke command ID so an interrupted run is not blindly repeated.

## Test-first sequence (one LIT unit iz3)

1. Add tests/test_voice_router.py for all contract/approval/router conditions,
   initially import-failing. Implement Interaction schema/codecs, journal
   admission and VM confirmation. Include journal reopen with mixed records,
   token replay/expiry/context mismatch and unchanged direct confirmation denial.
2. Implement runtime/voice/router.py. Test safe/risky/blocked/muted/stale catalog,
   aliases, ambiguity, malformed proposal, second-turn clarification, correction
   preview, all three confirmation channels, and no output/clipboard dependency.
3. Add runtime/voice/menu.py and ops/voice_smoke.py with subprocess-stub tests in
   tests/test_voice_smoke.py. Assert exact argv/no shell, one invocation maximum,
   timeout uncertainty, dry-run default and journal correlation.
4. Run full ResourceWarning-as-error suite and diff check; commit offline unit.
   Request one whole-branch Astra/high review, fix findings test-first, verify.
5. Run exactly one authorized live menu smoke with durable SQLite evidence.
   Read-only visibility/health query may corroborate; no retry on uncertainty.
   Record actual result in LIT and handoff, never claim UI visibility from exit
   code alone. Close iz3 only after required evidence passes.

Review focus: model data cannot confirm; pending tokens cannot reexecute; journal
failure before approval/intent prevents execution; stale focus/mute after proposal
blocks; live smoke cannot execute arbitrary command/arguments or repeat silently.
