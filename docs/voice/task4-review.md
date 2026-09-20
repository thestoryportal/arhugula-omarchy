# Task 4 repository-only safety review

Independent Astra/high review of `b2151f2..4b1b958`,2026-09-20. Reviewer used
read-only inspection and bounded synthetic probes, independently passed222
tests and6/6 coordinator replay cases. No live audio/provider/config changes.

Two Important findings, no Critical or Minor findings:

1. Activation cleared cancellation received during trusted-state callbacks,
   allowing capture or fresh-voice approval of a previously canceled preview.
   Fix: claim transition ownership before callbacks, clear only a previous
   ordinary turn's cancellation before preflight, recheck cancellation/token
   authority after callbacks. Tests reproduced microphone-adapter start and
   one fake execution after preview cancellation in both state-sampling windows.
2. Idle command cancellation unconditionally invalidated the shared owner,
   including successor dictation it could not clean or release.
   Fix: `SessionOwner.cancel(generation=...)` compares the owned generation
   atomically under its lock. Coordinator never globally cancels a shared owner.
   Tests reproduce idle command cancellation invalidating dictation and verify
   stale scoped cancellation preserves a successor owner.

Both findings reproduced RED, then focused session13/13 and coordinator24/24
GREEN after one fix pass. A controlled handoff-race test also failed when scoped
cancellation was deliberately replaced by global cancellation in a test-only
mutation probe; actual implementation passed. Full verification is in the handoff
and progress ledger. No second reviewer pass was substituted for regressions.

Rulings on reviewer exclusions (all remain later-gate limitations):

- Actual Home/End, cross-process exclusion, installation rollback and trigger
  deduplication are not implemented here. Consequence: no live cutover claim.
- Real Voxtype FILE/output/hook/network isolation bridge remains P2 work;
  injected jobs prove composition only. Consequence: no installed backend.
- Recorded ASR/VAD accuracy is not established by synthetic text or PCM.
  Consequence: retain the real-corpus acceptance gate.
- Compositor/device freshness and atomic actuation require trusted epochs and
  platform guards. Consequence: polling cannot authorize focus-sensitive output.
- Live microphone teardown timing, panel/keyboard surfaces and interruptible
  speech remain untested. Consequence: no live usability/release claim.

No deferred minor findings. Local Ruff was unavailable in both lead and Terra
environments; no dependency was installed. GitHub lint evidence is still needed
before integration, alongside current main/branch-policy reconciliation.
