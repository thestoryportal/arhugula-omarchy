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
counter. Admissions survive restart; a closed admitted predecessor with no completion
receipt holds the next admission for reconciliation. Implementation commits, source
GO and quarantines are not completions.
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
cannot be renamed for the same arc to reset the counter. Immutable ownership keeps
all prior arcs bound when a unit advances. Unit quarantine holds
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

The sixth ticket admission is held until a verified fresh epoch. The autonomous
`ops.orchestration.auto_reset` runtime service watches journal and native events
outside the model context. After five verified closed leaves, or an earlier measured
headroom hold, it prepares the package, waits for the actual parent turn to finish,
executes native `/clear` in the same bound Buford window and types/submits the whole
generated continuation prompt. The user does not clear or append a prompt.

Before finishing the boundary turn, save the actual `get_goal` tool result to a new
immutable receipt and release all owned writers. Record the release mechanically:

```bash
/home/robbo/Work/arhugula-build-eval/.venv/bin/python -m ops.orchestration.auto_reset release --config .local/buford-loop/autoreset-config.json --ownership <released-owner-receipt.json> --goal-receipt <actual-native-goal-receipt.json>
```

The release binds this UUID/epoch, every recorded completion, and the actual user
event count/hash. Even an identical repeated human message invalidates an older
release. A close arriving
before its matching release makes the service wait for the file event; it does not
exit or count an old release. Active owned PIDs refuse release and preparation.
Parent/epic closures never advance the five-ticket counter. The agent writes these
receipts as part of normal closure; there is no human handoff step.

The supervisor requires the actual idle Sol/high lane, unchanged latest human input
and pause/routing, sealed authority/source/goal bindings, exact window stable ID,
terminal/native PID start times and ancestry, and the US keyboard state. It directs
keys to that window without touching the clipboard or choosing another worker. A
nonce-named native title and the bound client's new, empty CLI rollout witness
clear before the full generated prompt is sent. Native-owned rollout discovery
does not depend on filesystem date partitions. Exact sealed prompt delivery and
one actual user message are required before bootstrap and receipt publication.
Persisted input intents hold uncertain deliveries for evidence-based recovery; no
blind replay erases an unrelated context. Native active-turn clear remains disabled.
The legacy generic `runner.py` and legacy session watcher are not enabled.

The external supervisor alone invokes `Loop.bootstrap`. The first automatic user
message instructs the fresh lane to verify `wait-bootstrap --config <config> --manifest
<sealed-manifest>`; do not bootstrap a second time. Bootstrap verifies new UUID,
Sol/high, creation time, CLI provenance and the nonce in the first actual user
message, reads LIT, and updates only Buford routing. Counts, review budgets,
quarantines and protected sessions survive. Atomic bootstrap recovery preserves one
epoch even if routing or receipt publication was interrupted.

The clear-to-bootstrap limit is 120 seconds; time spent waiting for an active
parent does not count. Full applicable Laws remain full-read once per fresh medium.
A live native trial must verify the actual receipt before production continues.
Historical HIL ask gates are superseded by the user's standing permission and latest
autonomous continuation instruction; a newer direct pause overrides them. Bootstrap
itself does not unpause production or assert installed acceptance.

Native goal counters belong to individual threads and cannot be imported by the
native setter. `GoalLineage` retains actual immutable receipts, the identical full
objective, original deadline and unbounded contract, and derives lifetime totals
across threads. Before publishing native acceptance, the supervisor reads the
outgoing completed thread's canonical `goals_1.sqlite` row in read-only mode and
retains its terminal snapshot, reconciling active-goal usage after the release
receipt. A changed native schema or nonterminal outgoing turn holds acceptance.
Same-thread updates use the latest monotonic totals, never count a
receipt twice or erase old usage with a fresh zero. The fresh lane reconciles its
actual native goal with that contract before work; it must not claim that native
counters were copied. Preserve the original receipts and never extend the deadline.

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
adapter's verification and worker execution paths use the same capture boundary.

Terminal receipts require successful fsync/hash readback and release of the owned
process group. A parent that leaves active descendants produces a failure receipt
after that group is stopped. Independently daemonized processes need a separate
lifecycle owner. A failed final directory sync removes the canonical receipt and
preserves its bytes under a publication-uncertain marker, which holds further
publication for explicit recovery. Interrupted, failed and timeout logs remain
preserved. Keep caches/venvs on guest ext4. This log publication
does not establish database WAL correctness, physical power-loss durability or S5
reset/restore acceptance on the Mac host.
