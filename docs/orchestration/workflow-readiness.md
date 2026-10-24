# Workflow readiness register

No live runtime scenario can start on this host today. Of the nine prerequisites
in specification WS-13 section 15.1, only the Mac artifact store is ready. Docker,
the telemetry stack, the offline embedding assets and host restore storage are
missing; the kernel/process execution route is denied; and the session roster,
toolchain shims and quiet-window resources each have a specific gap. Every entry
below names who resolves it and what would make it worth re-reading.

This is the WO-U18 register (plan WP-14; specification WS-13 15.1; verification
WT-18). Buford uses it to decide which scenarios can be scheduled. Runtime uses it
to check that a scenario's prerequisites hold before starting. Reviewers use it to
check that no missing or denied fact is being presented as a working capability.

Facts were read between 2026-10-24T00:05:22Z and 00:07:05Z by profile-coder
(Claude session `bcb70115-c73c-43ed-990b-e8d25a933c3b`) on the Omarchy guest
(`Linux 7.2.6-1-aarch64-ARCH`, aarch64). Raw output is in the Mac store:
`run-6t1wn5_p` holds the host probes and `run-707mnf5s` the session roster
measurement. The probe script itself is
`docs/orchestration/implementation-evidence/wo-u18-profile-coder-1/observe.sh` in
the root checkout.

## Reading an entry

**State** is one of `ready`, `missing`, `denied` or `unknown`, and it describes
capability: whether the thing works here and now. **Permission** is a separate field.
A standing authorization does not make a missing service ready. A working binary
does not make a denied action permitted. A success observed on another host or
an earlier date counts only as history.

A `denied` entry links to the retained denial record (`D1`–`D4` below). A denied
action is resolved only by approving that exact action through the normal approval
path. Changing the wrapper, flag, session, interpreter or host and trying again
is a covert retry, and it is not allowed. While an entry is held, the scenarios
that depend on it stay held and independent work continues.

## Register

### Native team sessions/reset service

- **State:** `missing`. The roster names a profile-coder session that is no longer
  the live one, and no session can be admitted for new substantial work right now.
- **Permission:** Buford owns roster rows and admission. Workers only read them.
- **Owner:** Buford.
- **Environment:** `docs/orchestration/session-control.json` in the root checkout,
  `repair_paused=false`, notification thread `01a16b35-4681-7f70-b7bc-fec750f95fb7`.
- **Evidence:** `run-707mnf5s` ran the existing `session_context admit` against
  all eight rows. Only profile-reviewer (`01a16b33`) measured `allow`. The
  profile-coder row still names `6bce438c`, which is complete and over the
  225,000-token ceiling at 230,310 tokens; the live profile-coder is `bcb70115`.
  Runtime (`f5422020`) has no request metric, so it cannot be measured. There is no
  central reset service: continuity is each lane's own Memento handoff in its
  existing Foot window, as `AGENTS.md` requires.
- **Resolution:** Buford updates the profile-coder row to `bcb70115` and measures
  admission at each assignment. An absent reset service stays a prerequisite; no
  replacement controller is built for it.
- **Dependent scenarios:** Any Runtime-witnessed scenario and any routed review
  handoff to profile-coder.
- **Revalidate when:** A lane clears or hands off through Memento, a roster row
  changes, or before any new assignment.

### Tools/runtime environment

- **State:** `missing`. The product Python environment works, but `uv` and `just`
  have no version on this host.
- **Permission:** Selecting a global tool version is an operator setting. Do not
  reinstall tools or substitute system Python for the product environment.
- **Owner:** Buford, with the operator for the mise global setting.
- **Environment:** Product `H` = `/home/robbo/Work/arhugula-build-eval` at local
  `origin/main` `91e76a4e22ffc0b013fa14a5d680d1c991f5a1e5`; existing venv
  `/home/robbo/Work/arhugula-build-eval/.venv`.
- **Evidence:** `run-6t1wn5_p`: the venv has Python 3.12.14, ruff 0.15.13,
  pyright 1.1.409 and pytest 9.0.3. `uv --version` and `just --version` both fail
  with "mise ERROR No version is set for shim"; mise suggests `uv@0.13.5` and
  `just@1.58.0`. Root tooling runs under the same venv Python; root CI separately
  proves Python 3.11 compatibility.
- **Resolution:** The operator sets the mise default to the versions the product
  lock expects, or Buford confirms that every scheduled command uses the venv's own
  executables. Either way, record the chosen versions here.
- **Dependent scenarios:** The 19-step build, any `just` recipe, any `uv sync` and
  the final installed matrix.
- **Revalidate when:** The mise configuration, the product lock file or the venv
  changes.

### Mac artifacts

- **State:** `ready` for raw log publication. This says nothing about restore or
  database durability; see Host storage/restore.
- **Permission:** Standing authorization covers raw logs in the private store.
- **Owner:** Buford.
- **Environment:** `/mnt/mac`, a 9p virtio share (`rw,relatime,cache=0x5`),
  store `/mnt/mac/arhugula-artifacts` (mode 0700).
- **Evidence:** `run-6t1wn5_p` was published through `ops.orchestration.artifacts`
  and read back with a matching stdout SHA-256 (`52d5b5df…`). `df` shows 43,232,280,576
  bytes free of 450,005,483,520, with 91 percent used.
- **Resolution:** None needed for publication. No document sets a free-space
  threshold, so each scenario contract must state its expected log volume, and
  Buford checks that against the free space measured before the run.
- **Dependent scenarios:** Every scenario, since raw logs must not fall back to
  guest disk.
- **Revalidate when:** Before each scenario run, after a guest reboot or remount,
  or when free space drops below a scenario's declared volume.

### Offline ARM models/embedding

- **State:** `missing`. The approved embedding asset is identified but not present,
  and the runtime libraries are not installed.
- **Permission:** The offline environment setup was denied (`D4`). That exact setup
  needs normal approval before anyone tries it again.
- **Owner:** Buford, with the user for the D4 approval.
- **Environment:** Product venv `/home/robbo/Work/arhugula-build-eval/.venv`
  (aarch64, Python 3.12.14); user cache `~/.cache`.
- **Evidence:** `run-6t1wn5_p`: `fastembed` and `onnxruntime` are not importable;
  `~/.cache/fastembed` does not exist and `~/.cache/huggingface` holds only `xet`;
  `ollama` is not on PATH and `ollama.service` is not installed (`systemctl` exit 4).
  The approved asset is `Qdrant/bge-small-en-v1.5-onnx-Q` at revision `aa8f8b06`;
  its five filenames come from repository metadata in
  `.local/24h-acceptance/a7-model-repo-api.json` (SHA-256 `e126f9a9…`). That file
  is not a model hash and not a no-network load. The A7 setup denial is
  `cmt-697c66ef`.
- **Resolution:** Request approval of the exact D4 setup action, then record the
  installed files, their checksums against the model's `SHA256SUMS`, and an
  observed offline load on aarch64.
- **Dependent scenarios:** The A7 offline embedding witness, local memory recall in
  the final installed matrix and any Ollama inference run.
- **Revalidate when:** D4 is resolved, the product lock changes the embedding
  extra, or the model cache changes.

### Docker/gVisor/live stack

- **State:** `missing`. Docker and containerd are installed but stopped and
  disabled, so there is no socket.
- **Permission:** Starting the services and granting socket access needs the
  user's normal Polkit authentication. `robbo` is not in the `docker` group.
- **Owner:** Buford for service setup, with the user for authentication.
- **Environment:** Guest services `docker.service` and `containerd.service`; gVisor
  binary `/usr/local/bin/runsc`.
- **Evidence:** `run-6t1wn5_p`: both services are `inactive` and `disabled`;
  `/run/docker.sock` is absent and `docker info` cannot connect; `runsc` is
  present. On 2026-10-05, Buford reached a running daemon through a temporary socket ACL
  (`cmt-5a471314`), and runsc was registered then (`cmt-75513c69`). That was a
  different session and is history, not current capability.
- **Resolution:** Buford starts the services through normal authentication, records
  the runtime list, image digests and owned containers, and states how they are
  cleaned up afterwards.
- **Dependent scenarios:** Live A3 tool runs under runsc, the telemetry stack, the
  real failure/recovery witnesses and the 60-minute soak.
- **Revalidate when:** A service state change, a guest reboot, or before any
  container scenario.

### Telemetry/subscription boundary

- **State:** `missing`. Subscription logins work, but the self-hosted telemetry
  stack is not running.
- **Permission:** Both CLIs use subscription logins. No paid API fallback is
  allowed. The telemetry stack runs only on loopback.
- **Owner:** Buford.
- **Environment:** The local Tempo, OTel Collector and Grafana stack that ran on
  loopback under Compose on 2026-09-30 (`cmt-1452e534`).
- **Evidence:** `run-6t1wn5_p`: `codex login status` reports a ChatGPT login and
  `claude auth status` reports a claude.ai first-party login. `ss -ltn` shows
  only DNS (53, 5355) and SSH (22) listeners; no telemetry port is open.
- **Resolution:** Start the stack after Docker is ready, using the pinned images,
  and record health checks and the exact endpoints.
- **Dependent scenarios:** Trace export checks in the final installed matrix and
  the soak.
- **Revalidate when:** Docker becomes ready, a login changes, or the stack's
  configuration changes.

### Kernel/process supervision

- **State:** `denied`. The execution routes these witnesses need were refused
  before they ran (`D1`, `D2`, `D3`).
- **Permission:** Denied. Only approval of each exact action through the normal
  path resolves it.
- **Owner:** Buford for the approval request; Runtime runs a witness only after
  that approval.
- **Environment:** This guest, under the Claude auto-mode permission classifier.
- **Evidence:** `D1` is the full48 recovery run, refused by the classifier
  (`.local/production-source09-01a10968/full48-recovery-01a10c0d/report.md`).
  `D2` is the corrected kernel/interpreter metadata witness, refused before
  execution as "[Auto-Mode Bypass]" (`cmt-17b26504`). `D3` is the W0 installed help
  recorder, refused the same way. A separate 2026-10-05 failure was an OS socket
  permission error, not a classifier denial, and it is history (`cmt-62c520a3`).
- **Resolution:** Request approval for each exact action as recorded. Do not retry
  through another wrapper, flag, session, interpreter or host.
- **Dependent scenarios:** Full48 membership, the kernel/interpreter provenance
  witness, W0 installed help sampling and supervision death/ownership proof.
- **Revalidate when:** A recorded approval for one of these exact actions exists.

### Host storage/restore

- **State:** `missing`. There is no retained block storage outside the guest's
  reset domain and no backup/restore proof.
- **Permission:** The storage choice belongs to the user, who deferred it
  (`cmt-dd621700`).
- **Owner:** The user, with Buford recording the decision.
- **Environment:** The Mac host and this guest. The guest has one disk, `/dev/vda`.
- **Evidence:** `run-6t1wn5_p`: `/` has 23,992,385,536 bytes free (82 percent
  used), down from about 65 GiB on 2026-10-02 (`cmt-6f515afd`). `/mnt/mac` is a 9p
  share used for raw logs. It is not retained storage for the memory database and
  does not prove restore. No S5 proof exists.
- **Resolution:** The user picks the retained storage and backup location; Buford
  then records a restore proof and the remaining gaps.
- **Dependent scenarios:** Memory database WAL durability, the S5 restore witness
  and the real failure/recovery witnesses.
- **Revalidate when:** The user decides on storage, or a new disk or share is
  attached.

### Quiet runtime resources

- **State:** `missing`. The host is busy with active agent lanes and no
  measurement window is reserved.
- **Permission:** Buford schedules runtime windows.
- **Owner:** Buford reserves the window; Runtime measures the baseline.
- **Environment:** This guest: 8 CPUs, 20,928,249,856 bytes of RAM and the guest
  disk above.
- **Evidence:** `run-6t1wn5_p`: load averages were 2.54, 3.33 and 2.84. In
  `run-707mnf5s`, four roster sessions measured `active`, and this session was
  running too. This register did not locate the original CPU, memory and storage
  pins. They belong to the accepted scenario contracts, and a later, larger memory
  reading must not replace them.
- **Resolution:** Reserve a window with the agent lanes idle, record a load baseline
  against the original pins, and keep that window for the quiet performance run.
- **Dependent scenarios:** Quiet performance, the final-main B-104/N1 run and the
  60-minute soak.
- **Revalidate when:** At the start of each reserved window.

## Retained denials

These records are immutable. The checker re-hashes them; a changed hash means the
record was altered and must be investigated, not re-recorded.

| ID | Path | SHA-256 | Denied action |
| --- | --- | --- | --- |
| D1 | `.local/production-source09-01a10968/full48-recovery-01a10c0d/actual-classifier-denial.json` | `5e743de3d06a53e4deadf75b2887d7d5de6b76c434a4d8c256ed3da6ac5d22d0` | full48 recovery pytest run through the artifact wrapper |
| D2 | `.local/production-source09-01a10968/kernel-interpreter-witness-01a10d8e/result.json` | `75af15b26805ed12abaf73ebea4bb0c7879dedf070c46ebaaed36cfd7f8892e5` | Byte-identical kernel/interpreter metadata witness |
| D3 | `.local/24h-acceptance/w0-runtime-denial.md` | `726a10989d6cd8e8544f9a5192d83221b8200dfcb1820850818cdf8da87a25c2` | W0 installed `harness --help` recorder |
| D4 | `.local/24h-acceptance/a7-author-report.md` | `99e30e9eb27eba1b71f278bc04f7c4e9f1b7b1b325452df0084d5cac0f0dd41f` | A7 offline venv setup with pinned uv (line 31) |

## Re-verifying this register

Run the probes again from the root checkout. Each run writes its raw output to a
new Mac store directory and prints the receipt:

```bash
python3 -m ops.orchestration.artifacts --cwd /home/robbo/Work/arhugula-omarchy --timeout 120 -- \
  bash docs/orchestration/implementation-evidence/wo-u18-profile-coder-1/observe.sh
python3 -m ops.orchestration.artifacts --cwd /home/robbo/Work/arhugula-omarchy --timeout 120 -- \
  python3 docs/orchestration/implementation-evidence/wo-u18-profile-coder-1/measure_roster.py
```

The structural check confirms that every 15.1 prerequisite has one entry with all
fields, that states are valid, that denials are linked and unchanged, and that the
artifact mount is not presented as restore readiness:

```bash
python3 docs/orchestration/implementation-evidence/wo-u18-profile-coder-1/check_register.py \
  docs/orchestration/workflow-readiness.md
```

These scripts are kept in the root checkout's evidence tree, not in this commit.
