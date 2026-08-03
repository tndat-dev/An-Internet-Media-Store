#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
policy="$root/audit/audit-policy.yaml"
node_script="$root/scripts/configure-audit-node.sh"
ssh_user=${AIMS_SSH_USER:-dat}

for binary in kubectl ssh scp jq; do
  command -v "$binary" >/dev/null || { echo "missing required command: $binary" >&2; exit 1; }
done

mapfile -t control_planes < <(
  kubectl get nodes -l node-role.kubernetes.io/control-plane -o json |
    jq -r '.items[] | [.metadata.name, ([.status.addresses[] | select(.type=="InternalIP")][0].address)] | @tsv' |
    sort
)
[[ ${#control_planes[@]} -ge 3 ]] || { echo "expected at least three control-plane nodes" >&2; exit 1; }

remote_sudo() {
  local ip=$1
  shift
  if [[ -n ${AIMS_SUDO_PASSWORD:-} ]]; then
    printf '%s\n' "$AIMS_SUDO_PASSWORD" |
      ssh "$ssh_user@$ip" "sudo -S -p '' $*"
  else
    ssh -t "$ssh_user@$ip" "sudo $*"
  fi
}

for entry in "${control_planes[@]}"; do
  IFS=$'\t' read -r node ip <<< "$entry"
  echo "configuring audit backend on $node ($ip)"
  scp -q "$policy" "$node_script" "$ssh_user@$ip:/tmp/"
  remote_sudo "$ip" /tmp/configure-audit-node.sh /tmp/audit-policy.yaml

  # kubelet restarts this static pod. Do not touch the next control-plane until
  # the API and this node are healthy again.
  healthy=false
  for _ in $(seq 1 60); do
    if kubectl get --raw=/readyz >/dev/null 2>&1 &&
       [[ $(kubectl get node "$node" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}') == True ]]; then
      healthy=true
      break
    fi
    sleep 5
  done
  if [[ "$healthy" != true ]]; then
    echo "API did not recover after audit change on $node; rolling back" >&2
    remote_sudo "$ip" /tmp/configure-audit-node.sh --rollback
    for _ in $(seq 1 60); do
      kubectl get --raw=/readyz >/dev/null 2>&1 && break
      sleep 5
    done
    kubectl get --raw=/readyz >/dev/null
    exit 1
  fi
  kubectl get --raw=/readyz >/dev/null
  kubectl get node "$node"
done

echo "audit logging configured on ${#control_planes[@]} control-plane nodes"
