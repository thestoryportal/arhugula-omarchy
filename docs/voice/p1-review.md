# P1 safety review, 2026-09-20

Scope: live-integration plan Tasks 1, 2 and the P1 portion of Task 3 only.
Independent reviewer: Astra/high, read-only, range 3dcceed..10b922c.
Reviewer independently passed 78 voice tests. No live provider/audio invocation.
Initial verdict: P1 merge with fixes; no Critical findings or deferred Minors.

## Important findings and one test-first fix pass

1. Thread construction/start after Popen could fail without terminating the
   child; later cancel could attempt to join an unstarted thread. Guard the
   ownership transfer and synchronously clean up the owned group on failure.
   Publish failed only after proven cleanup, otherwise uncertain.
2. Selector construction before the cleanup guard, or selector-close failure,
   could bypass child teardown and terminal result publication. Put initialization
   inside the guard; selector finalization failure must not bypass group cleanup.

Regression tests `test_supervisor_start_failure_reaps_child_and_cancel_remains_safe`
and `test_selector_resource_failures_reap_child_and_publish_terminal_result`
each exercised two failure points with real controlled Python children. All four
subcases failed before the fix. The fixed 17-test process suite and full 194-test
suite passed with ResourceWarning as error (1.453s and 8.329s respectively).
Tests check reaping, sanitized terminal status and repeated safe cancellation.
The RED tests recovered only their own controlled children; no live worker ran.
No second independent review was performed: the executing-plans skill requires
one fix pass with RED/GREEN regressions and whole-suite verification.

## Explicit rulings on review exclusions

- Home/End handoff and cross-process device exclusivity remain unimplemented,
  not implied by process-local ownership. Do not admit live capture before the
  coordinator/exclusion gates; cost is delayed live availability.
- Generation rejection at speech, preview and execution remains a Task 4
  integration requirement. The seams preserve generation and suppress canceled
  results, not end-to-end effects; cost is additional coordinator acceptance.
- Real Voxtype configuration, hooks, clipboard, typing and network isolation
  remain P2 blockers. Trusted injection is not a sandbox; cost is isolated
  characterization and possibly backend bridge work before any real inference.
- Fresh compositor/mute/device state and atomic external actuation remain Tasks
  4/6 requirements. Polling is not atomic output authorization; cost is blocking
  focus-sensitive effects until supported checks exist.
- Duplicate control triggers, partial installation and scoped restoration
  remain Tasks 5/7 requirements. No installation or control entrypoint is shipped
  by this P1 batch; cost is no deployment until these gates pass.
- Recorded-speech VAD/ASR accuracy, concrete TTS and actual confirmation surfaces
  remain separately gated and unproven. Synthetic replay cannot promote them;
  cost is more consented acceptance testing and possible provider redesign.

These are not deferred minor defects or claims of full voice completion.
The next step is .z5x.pab, labeled hil-required. Keep parent integration/voice
release open; preserve the branch and scratch workspace. Merge/push are held
while main contains foreign diagnostics, per the user's explicit direction.
