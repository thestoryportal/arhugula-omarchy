# Autonomous Buford context reset

Implement the user's explicit requirement: the clear after five completed tickets
and submission of the restart prompt must be autonomous, without HIL, before
production continues. Extend the installed loop; preserve its counters, canonical
review gates, Mac artifact boundary, full goal scope and original deadline.

## Native boundary

The existing Buford window is foot PID2785, stable ID18000003, address
0xaaab06051ed0. Its embedded Codex PID3335 launches gpt-6.1-sol/high. There is no
exposed Codex daemon control socket for this client. Native `/clear <name>` creates
a fresh chat in this same client and preserves the terminal. Do not substitute a
headless worker, resume, fork, another terminal or another named team session.

An external runtime service owns reset execution. Its configuration binds root,
native/terminal PID start times, window address/stable ID, Sol/high, actual user
authorization and a native goal receipt. Hyprland input goes to that exact window;
ASCII keys are derived for the verified US layout. It changes no focus, clipboard,
keyboard configuration, permissions or other window. Unsupported layout/caps lock,
changed process/window identity or native dispatch failure holds the action.

## Lifecycle

The service observes journal and native transcript events. A prepared reset waits
for actual `task_complete`, matching identity, unchanged authority/pause routing,
verified sealed files and released owned processes. No elapsed sleep constitutes
release. Five closed leaf receipts or a measured-headroom hold require preparation;
the native agent records ownership and its actual goal receipt automatically.

Persist intent before clear, observe the nonce-derived new chat title, persist
prompt intent, type the complete generated prompt and submit it. Discover the fresh
native transcript by creation time, cwd/provenance, nonce and actual model/effort.
The service invokes the existing mechanical `bootstrap` once and records a Mac
receipt. The fresh agent verifies that receipt instead of bootstrapping twice.
The clear-to-bootstrap deadline is 120 seconds. Uncertain delivery is held and
reported; it is never blindly replayed. Recovery after completed bootstrap derives
the receipt from its durable manifest/nonce binding without a second epoch.

The generated prompt includes the user's current autonomous-continuation authority;
the user appends nothing. Older HIL text does not revoke this newer instruction.
Production remains paused throughout source implementation/review. The first live
reset trial continues automatically into verification; production resumes only
after the source acceptance receipt and actual native reset receipt are verified.
Later direct user pauses/input invalidate an outgoing stale reset.

## Goal continuity

Native goals are thread-local and the public setter cannot import usage totals.
Retain each actual native goal receipt and derive lifetime totals across linked
epochs. Keep the original full objective, deadline and unbounded contract; never
edit a live objective to reset accounting or invent imported native counters.
Fresh agents reconcile the native goal with this durable lineage before resuming.
Original receipts, transcripts, worktrees, protected drafts and denials survive.

## Verification

Behavior tests cover active-turn exclusion, fifth-ticket preparation, changed
authority/routing/window/PID/layout, wrong fresh model/nonce, delivery uncertainty,
deadline expiry, crash after bootstrap, count preservation and goal lineage.
Exercise the actual Hyprland transport against an owned terminal fixture first.
Review the entire extension independently, fix meaningful defects with regressions,
run the full suite, install only owned files, then arm the real Buford trial.
No production action or success claim precedes the actual trial receipt.
