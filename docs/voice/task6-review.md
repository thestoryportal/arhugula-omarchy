# Task6 P1 review and disposition, 2026-09-20

Shared independent GPT-5.6 Terra/medium reviewer
`01a0bea6-e73c-7460-bee3-fc7b543f14d8` used the Superpowers code-review template
on immutable `6eb96e9..3f3be2764ed3e6f1398b4e3e905b6c4056fd24ca`.
Reviewer independently passed273 tests in9.737s in an isolated copy, zipapp
health and diff check. Initial verdict: with fixes. No Critical/Minor reported.

Two Important findings were addressed in one test-first fix pass:

1. Clock regression still inside a preview lifetime was accepted. Reviewer
   reproduced1000→1500→1200. Lead reproduced RED on view and confirmation;
   tracking the last observed clock prevents either path accepting the preview
   after any observed decrease. Clock recovery cannot resurrect it. Samples
   must catch up before new previews; reconnect does not reset the guard.
2. Coordinator cancellation left injected speech pending. Lead reproduced it
   and reviewer accepted the addendum as Important. Three RED regressions cover
   idle cancel, failed cleanup, and reentrant cancel during router speech.
   Cancellation/failure now includes speech cleanup; uncertain cleanup faults
   admission. A fourth test preserves normal clarification after capture owner
   release, preventing an overbroad fix from canceling legitimate output.

Final lead verification:278 tests in9.841s with ResourceWarning errors;
31 coordinator,15 panel,11 speech focused tests;6/6 synthetic coordinator cases;
runtime health and fresh zipapp health; clean diff check. No duplicate review
of the same range was requested. These are local results, not voice-branch CI
or successful main integration.

Rulings and costs retained by the Astra/high lead:

- P1 is the headless panel model, not a Tk window, installed keyboard listener,
  or packaged GUI. Cost: actual GUI/keyboard and deployment remain P8 work.
- The finite prompt catalog excludes dynamic router/catalog/model text. A
  future trusted binding selects a fixed prompt by reply type. Cost: no turnkey
  router-to-TTS runtime is claimed.
- Optional coordinator speech wiring preserves provider-free callers. Cost:
  future command and Home/End bindings must explicitly bind and honor cleanup;
  this does not prove cross-process microphone exclusion.
- Backend synthesis/playback cleanup and callback latency are trusted, bounded
  obligations. Cost: fake-backend tests cannot prove real provider cancellation,
  intelligibility, final actuation freshness or resource budgets.
- Reviewer excluded P4/P8 live provider, GUI and human acceptance. Those remain
  blocked/open, not waived. Cost: no usable live speech release from this unit.
- Python3.11 and Ruff were not run locally. Cost: protected PR CI, applicable
  final integration review and successful post-main CI remain required.

The user's preference is a more natural voice. No concrete provider/model was
selected or acquired. P4 decision `.z5x.8l3` remains HIL/needs-design. No live
audio, system configuration, installation or service operation was performed.
