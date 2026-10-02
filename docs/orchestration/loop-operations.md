# Buford loop boundaries

Use this controller in the existing visible lane. Production remains paused until
the user explicitly resumes it. The generic `runner.py` is not a visible-lane
replacement. The commands below use the existing product environment because the
canonical review reducer imports product dependencies; install nothing new.

Run from `/home/robbo/Work/arhugula-omarchy`:

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.loop status
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.loop begin <ticket>
```

`begin` reads LIT export and the selected ticket into retained Mac artifacts, checks
the production pause, actual Buford identity/model/effort and measured headroom,
then issues an admission ID. Run it at EVERY actionable loop iteration, including
startup, assignment, implementation-to-review, review-to-fix, shipping and closure.
Status polling of an already owned remote CI run is not a scheduling iteration.
Use `check <admission-id>` immediately before a consequential transition. A new
comment or changed pause/routing invalidates the admission. Stop on read failure;
context memory is not a fallback. Read new authoritative comment bodies from the
retained export, identified by issue/comment IDs. LIT status and claims remain live
authorities; the journal retains receipts, not a replacement backlog.

`--maintenance` permits the explicitly authorized optimization work during this
pause. It does not lift the pause or authorize production scheduling. `next` uses
native claims-first selection. If that candidate is quarantined it explicitly
filters the native ranked backlog, including native blocking and fresh foreign
claim markers, and records which selection source it used. `lit start` still
enforces claim ownership; never pass `--take` to automate a takeover.

After a closed leaf's required review, main landing and post-main CI are verified,
record `complete <ticket> --evidence <closure-receipt>`. The command rereads LIT,
requires the actual closed leaf and its prior admission, binds the receipt hash and
counts that ticket once across restart. Parent/epic closure does not advance the
counter. Implementation commits, source GO and quarantines are not completions.
The current goal's source shipping units share a still-open LIT ticket; they do not
pretend to be separately closed tickets. Measured headroom can trigger an earlier
reset while that ticket is still in progress.

## Review ceiling

Before launching a review and after delivering/adjudicating a pass:

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.loop review <ticket> --product <shipping-worktree> --arc <stable-arc>
```

The canonical product reducer supplies complete pass bindings and the next
mandatory pass. The five-pass upper bound is per stable LIT ticket (or explicit
`--unit` under a multi-unit goal) across arcs, PRs, heads and context clears. Supply
the same `--unit` to `begin` and `review`; unit identity is recorded in LIT and
cannot be renamed for the same arc to reset the counter. Unit quarantine holds
that unit while independent units under the still-open goal remain available.
Partial passes and REVIEWER_UNAVAILABLE do not
count. No sixth launch is admitted. Preserve the canonical earlier two consecutive
pass-3 P1 stop. A budget is a scheduling limit, never permission to merge a P1.

Every finding retains its canonical disposition. Independently adjudicated
P2/P3 prose with no behavioral impact may be supplied in an `--impacts` JSON file
with `finding_id`, `impact: prose_no_behavior`, `actor`, exact `producer` and
`evidence` pointer; self-adjudication is refused. Keep the canonical follow-up row
and recorded explanation. P1 is never prose-excused. Severity alone never excuses
substantive P2. Incomplete mandatory review or blocking findings at the ceiling
quarantine the ticket, preserving the worktree and unmerged branch. The journal and
LIT label `review-quarantined` hold it; selector also excludes children and dependent
work. Select the next independent native LIT candidate. No automated budget
extension or operator-consent request is generated.

`code_verified` describes review completion only. Independently required CI,
unchanged merge door, landing, post-main CI and installed acceptance still apply.
The controller verifies gate-only landing deltas with the canonical landing-delta
producer before applying a reviewed binding to the final head. Do not rerun a completed
review solely because recording its verdict added gate rows.

## Five-ticket clear boundary

The sixth ticket admission is held until a verified fresh epoch. Do not postpone
the boundary because the next ticket looks small. Prepare from incremental receipts:

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.loop prepare-clear <new-private-directory> --ownership <released-owner-receipt.json>
```

The owner receipt supplies `owned_processes` (an explicit list of PID objects,
empty only after release). Live owned PIDs refuse preparation. The package seals
a bounded frontier and ready-to-paste prompt, retaining the full production
handoff by SHA256 reference rather than rewriting its history. Preparing does not
clear an active parent turn. After the parent finishes, an external caller runs:

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.loop ready-clear --transcript <current-native-transcript>
```

Only an idle identity-matched lane with a sealed package is clearable. Use native
`/clear` in that same visible window, retaining `gpt-6.1-sol/high`, then paste the
sealed prompt. The controller does not simulate terminal input or use `codex exec`
as a replacement session. Automated GUI clear is not enabled: the current TUI has
no verified control socket, and active-turn clear is disabled. The scheduling stop
is deterministic; the native clear requires this idle external step.

In the fresh lane `bootstrap --transcript <actual-new-transcript>` verifies seals,
the actual new UUID/model/effort and fresh LIT reads before updating only Buford
routing. All completed-ticket and review receipts survive. Atomic intent permits
recovery if routing updated but the journal did not. The original pause, deadline,
scope and goal accounting survive; do not create a smaller or reset goal. Retrieve
the actual native goal and reconcile its sealed predecessor receipt if a native
thread change requires transfer. Bootstrap does not resume the production goal.

The mechanical bootstrap deadline is 120 seconds; timeout leaves work held. Its
receipt measures actual time. Mandatory full Laws and applicable product skills
are loaded once per fresh medium and are not replaced by compact summaries. No
claim of an observed two-minute end-to-end TUI restart is made before that restart.

## Raw artifacts

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.artifacts --cwd <owned-worktree> --timeout 1800 -- <literal-command> <arguments>
```

Use this for compilation, tests and runtime commands. Raw stdout/stderr stream to
private files under `/mnt/mac/arhugula-artifacts`; only bounded failure extracts,
exit, hashes, sizes, time and pointers return. Full verdicts/findings must be
consumed from their structured files and must not be inferred from a truncated log.
The default checks the real writable `mac` 9p mount; an unavailable/read-only share
fails before command execution. An explicit alternative `--root` is for test stores
or deliberately recorded recovery, never an automatic fallback. The existing local
adapter's verification path uses the same capture boundary.

Terminal receipts require successful fsync/hash readback. Interrupted, failed and
timeout logs remain preserved. Keep caches/venvs on guest ext4. This log publication
does not establish database WAL correctness, physical power-loss durability or S5
reset/restore acceptance on the Mac host.
