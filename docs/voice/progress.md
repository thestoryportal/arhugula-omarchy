# Voice execution ledger

Baseline ec4e9a2; branch feat/voice-core-contracts; isolated .worktrees/voice-core.
Approved workspace spec/plan B.1+ and refined voice-adapter-contracts design.
No live services, configuration, audio or app output authorized.

v1t: RED missing runtime.voice; implemented injected dictation state machine.
Direct/fallback output, focus changes, provider gates, service failure, cancel,
failed cleanup, observer errors and callback reentrancy covered. Reentrancy
regressions first failed (nested capture started), then busy-state ordering fixed.
Raw transcription/audio and exception contents excluded from notices/results.
Clipboard fallback is copy-only; uncertainty never causes duplicate output.

f5v: Terra/medium sole writer 93c6f60; 104 tests initially passed. Independent
Terra review found terminal-token loss; test-first fix 9245803 and scoped review
clean. Coordinator full suite 105/105 passed. Capture bounds, silence adaptation,
cancel, stale tokens and synthetic replay verified; no actual VAD/audio claims.
Ruling: synthetic fixture replay is not real audio/VAD validation; no user audio
provided or captured. Cost if wrong: add approved recordings at integration.

User subsequently authorized one live Omarchy-menu smoke after offline checks,
without configuration/service changes. iz3 may use only `omarchy menu summon
root` once; no microphone, bindings, service changes or general desktop actions.

iz3 offline implementation: VM confirmation tokens and Interaction journal kind;
data-only candidate routing, clarification, correction preview and three trusted
confirmation channels; narrow fixed-argv menu executor and dry-run smoke CLI.
RED imports plus context-binding/state-service/inferred-execution regressions.
Ruling: inferred/fuzzy proposals always preview even at high confidence — lexical
similarity can misread negation — cost is one extra confirmation, not surprise IO.
Live smoke was held until independent review and its fix round passed.

Whole-branch Astra/high review of ec4e9a2..ad686a9 found R1 shared/reopened
preview bypass, R2 state freshness after blocking journal operations and before
speech, and R3 generic context source bypassing voice profile gating. A single
Astra/high fix wave 8abd0f1 reproduced 13 failing assertions and passed 27 focused
and 137 full-suite tests. Fixes persist restrictive preview observations, carry
trusted state guards through dispatch/confirmation, recheck before speech, and
stamp voice provenance. Final scoped re-review addressed R1-R3 with no new
Critical/Important findings; reviewer independently passed 27 focused tests.

The one authorized menu smoke succeeded on 2026-09-20 at implementation HEAD
d591b15. The fixed executor acknowledged the request; a separate read-only
Hyprland layers query observed one omarchy-menu surface (zero before). Durable
SQLite records contain exactly command.started/pending then command.finished/
success, with integrity_check=ok. See live-smoke.json. The authorization is now
consumed: do not launch again, switch journal paths, or interpret this as speech
acceptance. No config, service, audio, clipboard or typing changes were made.

Review deferrals are explicit: actual mic/VAD/Whisper/TTS, atomic platform output,
physical-device arbitration, synchronous-transcription interruption and complete
live speech release are not established by mock/synthetic tests. Network tools
are not exposed. All remain subject to the original authority boundary. A menu
smoke establishes the typed executor only; o19 must not claim a live voice release
without authorized bindings and recorded/live speech acceptance.
