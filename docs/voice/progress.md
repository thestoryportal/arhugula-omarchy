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
