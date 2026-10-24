#!/usr/bin/env bash
# Read-only probes behind docs/orchestration/workflow-readiness.md. Run from
# canonical O through ops.orchestration.artifacts so the raw output lands in the
# Mac store.
#
# [LAW:no-silent-failure] Probes that are expected to fail on this host (docker
# info against an absent socket, unset mise shims) are still run and their exit
# status is printed beside their output. Nothing is suppressed or defaulted; the
# register cites these exit codes as evidence.
#
# Every command here only reads state. Nothing starts a service, changes a
# permission, installs a package or downloads a model.
set -u

H=/home/robbo/Work/arhugula-build-eval
O=/home/robbo/Work/arhugula-omarchy

probe() {
  printf '\n$ %s\n' "$*"
  "$@" 2>&1
  printf 'exit=%s\n' "$?"
}

probe date -u +%FT%TZ
probe uname -srm

printf '\n## Tools/runtime environment\n'
probe "$H/.venv/bin/python" --version
probe "$H/.venv/bin/ruff" --version
probe "$H/.venv/bin/pyright" --version
probe "$H/.venv/bin/python" -m pytest --version
# The mise shims and the installed binaries are separate facts: the shims need a
# selected version, the binaries do not.
probe uv --version
probe just --version
probe "$HOME/.local/share/mise/installs/uv/0.13.5/uv-aarch64-unknown-linux-gnu/uv" --version
probe "$HOME/.local/share/mise/installs/just/1.58.0/just" --version
probe /usr/bin/python3 --version
probe git -C "$H" rev-parse origin/main

printf '\n## Offline ARM models/embedding\n'
probe "$H/.venv/bin/python" -c 'import importlib.util as u; [print(m, u.find_spec(m) is not None) for m in ("fastembed", "onnxruntime")]'
probe ls -la "$HOME/.cache/huggingface"
probe ls -d "$HOME/.cache/fastembed"
probe sha256sum "$O/.local/24h-acceptance/a7-model-repo-api.json"
probe bash -c 'command -v ollama'

printf '\n## Docker/gVisor/live stack\n'
probe systemctl is-active docker.service containerd.service
probe systemctl is-enabled docker.service containerd.service
probe ls -l /run/docker.sock
probe id -nG
probe docker info --format '{{.ServerVersion}}'
probe ls -l /usr/local/bin/runsc
probe systemctl is-active ollama.service

printf '\n## Telemetry/subscription boundary\n'
probe ss -ltn
probe codex login status
# The status JSON names the login method only; it carries no token.
probe claude auth status

printf '\n## Mac artifacts and host storage\n'
probe findmnt -no SOURCE,FSTYPE,OPTIONS /mnt/mac
probe df -B1 / /mnt/mac

printf '\n## Quiet runtime resources\n'
probe nproc
probe free -b
probe cat /proc/loadavg

printf '\n## Kernel/process supervision: retained denials (read, never retried)\n'
probe sha256sum \
  "$O/.local/production-source09-01a10968/full48-recovery-01a10c0d/actual-classifier-denial.json" \
  "$O/.local/production-source09-01a10968/full48-recovery-01a10c0d/report.md" \
  "$O/.local/production-source09-01a10968/kernel-interpreter-witness-01a10d8e/result.json" \
  "$O/.local/24h-acceptance/w0-runtime-denial.md"
