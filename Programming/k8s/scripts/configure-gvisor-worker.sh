#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

install -d -m 0755 /usr/share/keyrings /etc/apt/sources.list.d
if [[ ! -s /usr/share/keyrings/gvisor-archive-keyring.gpg ]]; then
  curl -fsSL https://gvisor.dev/archive.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/gvisor-archive-keyring.gpg
fi

arch="$(dpkg --print-architecture)"
printf '%s\n' "deb [arch=${arch} signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  > /etc/apt/sources.list.d/gvisor.list
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y runsc

config=/etc/containerd/config.toml
if ! grep -q "runtimes.runsc" "$config"; then
  cp -a "$config" "${config}.aims-backup"
  printf '\n%s\n%s\n' \
    "[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runsc]" \
    "  runtime_type = 'io.containerd.runsc.v1'" >> "$config"
fi

systemctl restart containerd
systemctl restart kubelet
systemctl is-active --quiet containerd
systemctl is-active --quiet kubelet
runsc --version | head -n 1

