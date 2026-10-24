#!/usr/bin/env bash
# WO-U22 read-only capability observation for the transient-service/cgroup boundary.
# Reads manager, cgroup and delegation state only; starts no unit and signals nothing.
set -u
run() { printf '\n$ %s\n' "$*"; "$@"; printf '[exit %s]\n' "$?"; }
run date -u +%FT%TZ
run uname -srm
run systemctl --version
run systemd-run --version
run systemctl --user is-system-running
run systemctl is-system-running
run stat -f -c %T /sys/fs/cgroup
run cat /proc/self/cgroup
run cat /sys/fs/cgroup/cgroup.controllers
run systemctl show "user@$(id -u).service" -p Delegate -p DelegateControllers -p ActiveState
run cat "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers"
run cat "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.subtree_control"
run systemctl --user show -p Version -p DefaultTimeoutStopUSec -p DefaultLimitNPROC
run systemctl --user list-units --type=scope --type=service --state=running --no-legend --plain
run loginctl show-user "$(id -u)" -p Linger -p State
