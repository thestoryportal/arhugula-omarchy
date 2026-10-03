# Buford autonomous reset implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkboxes.

**Goal:** Clear the existing visible Buford lane and submit its complete continuation
prompt automatically after five closed tickets or an earlier context hold.

**Architecture:** A runtime supervisor outside the model context uses a bound native
window transport and the existing sealed journal/bootstrap boundary. Native evidence
acknowledges transitions; immutable goal receipts retain lifetime accounting.

**Tech Stack:** Python standard library, existing product environment, Hyprland 0.56,
embedded Codex 0.159.2, transient systemd user service, physical Mac artifact store.

**Spec:** `docs/superpowers/specs/2026-10-02-buford-autoreset-design.md`.

## Global Constraints

- No production work before source acceptance and actual native reset verification.
- Same window/client; gpt-6.1-sol/high; no manual clear or prompt append.
- Preserve full goal scope, original 2026-10-02T05:06:38Z deadline, receipts and counters.
- Persist effects' intents, refuse blind replay, enforce 120-second native reset deadline.
- Raw execution evidence stays on /mnt/mac/arhugula-artifacts.

## Review Focus

- Native task completion followed by a new turn or new human message must refuse stale reset.
- Window/PID reuse or unsupported keyboard state must never direct input elsewhere.
- Crash between native clear/prompt effects must not erase another fresh context.
- Old HIL text must not require human resumption after verified authorized bootstrap.
- Fresh thread-local native counters must not erase lifetime goal usage or imply imported totals.

### Task 1: Bound native window transport

**Files:** create `ops/orchestration/native_window.py`, `tests/test_native_window.py`.
**Interfaces:** `WindowCapability` binds window/process identity; `NativeWindow`
reads actual state and delivers a literal ASCII line to that exact window.

- [x] Write tests for address/PID reuse, layout/caps refusal and literal key delivery.
- [x] Run them RED; implement the boundary; run GREEN.
- [x] Run actual owned-terminal transport witness; retain raw receipt; commit.

### Task 2: Autonomous reset lifecycle and goal lineage

**Files:** create `ops/orchestration/auto_reset.py`, `ops/orchestration/goal_lineage.py`,
`tests/test_auto_reset.py`, `tests/test_goal_lineage.py`; modify `loop.py`.
**Interfaces:** supervisor consumes prepared reset plus actual user/goal/window
bindings, uses native transport, invokes `Loop.bootstrap`, and publishes a verified
native receipt. `GoalLineage.record` consumes actual native receipts and derives totals.

- [x] Write behavioral tests for active/stale/uncertain/deadline/recovery/fifth boundaries.
- [x] Observe RED; implement persistent effects and fully generated continuation text.
- [x] Verify GREEN with real journal/bootstrap and independent external seams; commit.

### Task 3: Adoption, independent review and actual native trial

**Files:** operational docs/root admission instructions; private authority/config,
source-acceptance and native-trial receipts under `.local/buford-loop/`.
**Interfaces:** runtime service starts outside the active parent; generated first
message verifies acceptance and continues without human append or new permission gate.

- [x] Run full suite and obtain one fresh independent whole-extension review.
- [x] Resolve meaningful defects with RED-to-GREEN regressions and a green suite.
- [ ] Install only owned changes, record LIT evidence and preserve existing sealed packages.
- [ ] Arm live same-window reset after this parent becomes idle; fresh context verifies
  its actual receipt and continues acceptance/production autonomously.

The user's explicit no-HIL instruction and standing advance approval supersede
skill permission gates. Preserve the previously selected inline method and bounded
independent reviewer; do not substitute named worker windows.
