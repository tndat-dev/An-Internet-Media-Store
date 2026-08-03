#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "Run as root: sudo $0 <seccomp-json> <apparmor-profile>" >&2
  exit 1
fi
if (( $# != 2 )); then
  echo "Usage: $0 <seccomp-json> <apparmor-profile>" >&2
  exit 2
fi

install -D -m 0644 "$1" /var/lib/kubelet/seccomp/profiles/aims-runtime.json
install -D -m 0644 "$2" /etc/apparmor.d/aims-restricted
apparmor_parser -r /etc/apparmor.d/aims-restricted

test -s /var/lib/kubelet/seccomp/profiles/aims-runtime.json
aa-status | grep -q aims-restricted
echo "Installed AIMS seccomp and AppArmor profiles on $(hostname)"
