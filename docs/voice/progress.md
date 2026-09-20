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
