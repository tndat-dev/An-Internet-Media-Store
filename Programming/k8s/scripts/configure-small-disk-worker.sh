#!/usr/bin/env bash
set -euo pipefail

# Set AIMS_EVICTION_PERCENT=5 only for a constrained lab disk. After expansion,
# invoke with 10 (or 15) to restore a production-safe reserve.
eviction_percent="${AIMS_EVICTION_PERCENT:-5}"
case "${eviction_percent}" in
  5|10|15) ;;
  *) echo "AIMS_EVICTION_PERCENT must be 5, 10 or 15" >&2; exit 2 ;;
esac

KUBELET_ARGS="--eviction-hard=memory.available<100Mi,nodefs.available<${eviction_percent}%,nodefs.inodesFree<5%,imagefs.available<${eviction_percent}%,imagefs.inodesFree<5%,pid.available<10% --eviction-pressure-transition-period=30s"

if [[ ! -e /etc/default/kubelet.aims-backup ]]; then
  sudo install -m 0644 /etc/default/kubelet /etc/default/kubelet.aims-backup
fi
sudo sed -i "s|^KUBELET_EXTRA_ARGS=.*|KUBELET_EXTRA_ARGS='${KUBELET_ARGS}'|" /etc/default/kubelet
sudo systemctl daemon-reload
sudo systemctl restart kubelet
sudo systemctl is-active --quiet kubelet

echo "Configured kubelet ${eviction_percent}% disk eviction thresholds on $(hostname)"
