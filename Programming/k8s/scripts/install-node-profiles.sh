#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=${1:-/tmp}

install -d -m 0755 /var/lib/kubelet/seccomp/profiles
install -m 0644 "${SOURCE_DIR}/aims-runtime.json" \
  /var/lib/kubelet/seccomp/profiles/aims-runtime.json
install -m 0644 "${SOURCE_DIR}/aims-restricted.apparmor" \
  /etc/apparmor.d/aims-restricted

apparmor_parser -r -W /etc/apparmor.d/aims-restricted
test -x /usr/bin/runsc
grep -q "runtimes.runsc" /etc/containerd/config.toml

echo "Installed AIMS seccomp/AppArmor profiles and verified runsc on $(hostname)"
