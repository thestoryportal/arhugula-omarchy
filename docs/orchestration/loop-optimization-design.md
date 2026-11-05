# Buford loop optimization design

Implement the user's four optimizations before resuming production work. Keep
`arhugula-harness-trial-193` paused, its original deadline and full scope intact.
No shipping worktree, protected draft, gate evidence or worker session is altered.

The visible lane uses a boundary CLI, not the generic noninteractive worker runner.
Each scheduling/transition iteration reads native LIT export and the active ticket;
the CLI saves full reads to artifacts and emits bounded pointers. Required reads
fail closed. A ticket fingerprint includes comment IDs and bodies, not just the
issue's updated timestamp. A transition rereads LIT to detect concurrent changes.

An atomic, lease-protected journal retains completion receipts keyed by ticket ID,
review bindings and session epochs; it does not replace LIT status. Five distinct
verified closed leaf tickets in an epoch require a fresh native context before a
sixth admission. An earlier measured-headroom hold is allowed. Preparing a clear
seals a small manifest and ready-to-paste prompt, preserving the original goal
handoff by immutable reference. Bootstrap rereads LIT, verifies actual transcript
UUID/model/effort and changes only Buford routing. The controller never types
`/clear` into an active TUI; the idle native boundary is explicit. A 120-second
mechanical bootstrap deadline fails closed; measured latency is reported separately
from the time spent loading mandatory Laws. Epoch changes preserve goal accounting.

Review counts derive from product `tools/review_loop_gate.py::pass_runs`, including
its exact reviewer sets and bindings. Only completed review passes count; unavailable
reviewers do not. The upper bound is five completed passes per stable ticket across
arcs/PRs/clears. Canonical earlier stops remain. Every finding is logged and
adjudicated; independently evidenced P2/P3 prose with no implementation impact is
follow-up work. Substantive P2 remains blocking wherever the canonical gate requires
it. Known P1 cannot merge. At the ceiling, unresolved P1 quarantines the ticket;
incomplete mandatory review or substantive P2 holds it as well. Selection excludes
quarantined tickets and their dependency/parent scope; native LIT candidates are
queried with those exclusions, never replaced by a homemade priority ordering.
Review clearance is distinct from CI, landing, post-main CI and installed acceptance.

Raw compiler, test and runtime output streams to private files on
`/mnt/mac/arhugula-artifacts`. A mount check refuses the guest root filesystem
masquerading as that share. Receipts bind argv, cwd, terminal exit, byte counts,
SHA256 and elapsed time. Bounded summaries contain exits, counts and failure
extracts; full findings/verdict records are separately consumed without truncation.
No memory buffering of raw output, silent fallback or log deletion. Share failures
hold completion; fsync/hash-readback is log publication evidence, not S5 acceptance.

Tests cover fifth/sixth admissions, duplicate receipts, restart recovery, changed
comments, failed LIT reads, wrong model/UUID, active-writer clear refusal, review
budget across histories, quarantine/dependent selection, large output, timeout and
share failure. Use standard-library Python and existing lease/atomic-handoff seams.
