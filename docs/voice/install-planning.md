# Voice cutover planning: offline P1 only

`ops.voice_install_plan.plan_install(current_hashes, approved_hashes,
target_version)` produces a deterministic JSON-compatible review proposal.
It reads no files, starts no processes and makes no changes. It is **not an
installer**, does not authorize cutover and always reports `ready_to_apply=false`.
It cannot validate the truth, freshness or human approval of supplied snapshots.

## Snapshot contract

This first plan is pinned to the host paths in the approved live-integration
proposal. Both snapshots must include SHA-256 lowercase hex digests for all seven
baseline files under `/home/robbo/`:

- `.config/hypr/bindings.lua`
- `.config/systemd/user/voxtype.service`
- `.config/systemd/user/voxtype-commands.service`
- `.config/voxtype/config.toml`
- `.config/voxtype/commands.toml`
- `.local/bin/omarchy-voice-command-trigger`
- `.local/bin/omarchy-voice-commands`

`approved_hashes` contains exactly those seven paths. `current_hashes` additionally
contains these six new destinations, each explicitly set to JSON `null`/Python
`None` to attest absence (not merely missing from the snapshot):

- `.config/systemd/user/arhugula-voice.service`
- `.config/arhugula/voice.json`
- `.local/share/arhugula/voice-<target_version>.pyz`
- `.local/bin/arhugula-voice-home`
- `.local/bin/arhugula-voice-end`
- `.local/bin/arhugula-voice-command`

Keys are full absolute paths. Version is 1–64 ASCII letters/digits/dot/underscore/
hyphen, starting with a letter or digit. Unknown paths, missing observations,
invalid hashes, drift or any occupied destination reject the entire proposal.
Errors contain finite codes, not file contents or caller-provided values.

An eventual trusted inventory must reject symlinks (including dangling symlinks),
nonregular files, unsafe parent directories and races; `exists()` alone cannot
establish absence. That inventory and a transactional installer are not implemented
here. Never interpret uninspected, unreadable or symlinked paths as `None`.
Creating both dictionaries from current state is not an independent approval.

## Proposed changes and preserved behavior

Only HOME, END and KP_EQUAL entries in bindings.lua may be modified. Every old
key is explicitly unbound before its replacement. All other binding bytes,
legacy scripts, Voxtype profiles and service definitions are preserved. No
packaged Omarchy path is a target. The new wrappers are **contracts**, not yet
working implementations:

- HOME: cancel command work, prove owned-child cleanup, then forward existing
  `voxtype record start`. Failure must not start dictation beside command capture.
- END: require dictation ownership, then forward existing `voxtype record stop`.
- KP_EQUAL: one coordinator-owned command activation; no automatic action retry.

The plan is repeatable against an unchanged snapshot. After even one proposed
addition or binding modification, the old approved snapshot rejects. This avoids
silently stacking handlers; it is not a lock against concurrent installers.

`ops/templates/voice-bindings.lua` is entirely commented; loading it does nothing.
`ops/templates/arhugula-voice.service` intentionally uses `/usr/bin/false`, has
`Restart=no`, and no login enablement section. These are review placeholders,
not deployable services. Do not substitute the existing runtime-only zipapp for
the proposed voice artifact: it does not yet package the panel/foreground wiring.

## Rollback proposal and remaining gates

The rollback proposal starts with disabling command admission and proving owned
child cleanup. Every operation is restricted to a named changed path and requires
its current hash to match an **owned installation receipt**. Restore only the
owned binding diff from recorded originals; remove only an owned addition.
Installed hashes are deliberately unset and `rollback.ready=false`: this plan
cannot manufacture a receipt for an installation that never occurred. Refuse
drift or missing evidence; never overwrite unrelated edits or blindly restore
an entire configuration tree. Retain recovery files.

An authorized future cutover must supply exact reviewed artifact/config/wrapper
bytes and hashes, scoped diff, originals, parent-directory validation, prior
service active/enabled state and live ownership/acceptance evidence. Binding
apply/restore then requires `hyprctl reload` and `hyprctl configerrors`; neither
is run by this planner. Restore only previously active legacy services and only
after cleanup proof. Start, disable and login-enable decisions remain separately
scoped. No actual rollback, audio or desktop acceptance is claimed here.

Task7 P1 tests are offline synthetic fixtures. P2 corpus/FILE adapter, concrete
P4 TTS and actual P3/P5–P8 live acceptance remain separate unfinished work.

## Continuous work and honest closure

The renewed operator instruction permits continuous authorized repository work
across unit/arc boundaries without routine HIL prompts. It does not turn snapshot
data into deployment authority. Skip a blocked live slice in favor of a safe
unimplemented P1 unit; record that selection in LIT rather than redoing a completed
implementation or prematurely closing an arc.

Claim with `lit start`, maintain one writer per ticket/files, test and review an
immutable commit range, record LIT evidence, commit and hand off. Keep locally
verified work `awaiting-integration` until protected main landing and successful
post-merge CI. Agent review and Astra signoff are evidence, not merge authority.
Root owns push, PR, CI, merge, and post-main CI; no separate GitHub-user approval
is required. Consult
the handoff before following claims-first `lit next`: it can return an implemented
unit that awaits integration rather than new coding work.
