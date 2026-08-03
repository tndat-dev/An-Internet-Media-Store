#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

backup_root=/var/backups/kubernetes
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$backup_root/cis-$timestamp"

harden_file() {
  local path=$1
  [[ -e "$path" ]] || return 0
  chown root:root "$path"
  chmod 0600 "$path"
  echo "hardened permissions: $path"
}

inject_command_flag() {
  local manifest=$1 binary=$2 flag=$3
  [[ -f "$manifest" ]] || return 0
  grep -qF -- "$flag" "$manifest" && return 0

  install -d -m 0700 "$backup_dir"
  cp -a --update=none "$manifest" "$backup_dir/$(basename "$manifest")"

  local tmp
  tmp=$(mktemp)
  awk -v binary="$binary" -v flag="$flag" '
    $0 ~ "^[[:space:]]*- " binary "$" {
      print
      match($0, /^[[:space:]]*/)
      indent=substr($0, RSTART, RLENGTH)
      print indent "- " flag
      injected=1
      next
    }
    {print}
    END {if (!injected) exit 42}
  ' "$manifest" > "$tmp" || {
    rc=$?
    rm -f "$tmp"
    echo "failed to locate $binary in $manifest (rc=$rc)" >&2
    exit "$rc"
  }
  install -m 0600 "$tmp" "$manifest"
  rm -f "$tmp"
  echo "injected $flag into $manifest"
}

ensure_command_flag_value() {
  local manifest=$1 prefix=$2 desired=$3
  [[ -f "$manifest" ]] || return 0
  grep -qF -- "$desired" "$manifest" && return 0
  if ! grep -qF -- "$prefix" "$manifest"; then
    echo "missing existing flag prefix $prefix in $manifest" >&2
    exit 1
  fi

  install -d -m 0700 "$backup_dir"
  cp -a --update=none "$manifest" "$backup_dir/$(basename "$manifest")"
  local tmp
  tmp=$(mktemp)
  awk -v prefix="$prefix" -v desired="$desired" '
    index($0, "- " prefix) {
      match($0, /^[[:space:]]*/)
      indent=substr($0, RSTART, RLENGTH)
      print indent "- " desired
      replaced=1
      next
    }
    {print}
    END {if (!replaced) exit 42}
  ' "$manifest" > "$tmp" || {
    rc=$?
    rm -f "$tmp"
    echo "failed to replace $prefix in $manifest (rc=$rc)" >&2
    exit "$rc"
  }
  install -m 0600 "$tmp" "$manifest"
  rm -f "$tmp"
  echo "set $desired in $manifest"
}

harden_file /var/lib/kubelet/config.yaml
kubelet_unit=$(systemctl show kubelet -p FragmentPath --value)
[[ -n "$kubelet_unit" ]] && harden_file "$kubelet_unit"
harden_file /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf
if [[ -f /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf ]]; then
  install -d -m 0755 /etc/systemd/system/kubelet.service.d
  benchmark_dropin=/etc/systemd/system/kubelet.service.d/10-kubeadm.conf
  [[ -L "$benchmark_dropin" ]] && unlink "$benchmark_dropin"
  install -m 0600 \
    /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf \
    "$benchmark_dropin"
  echo "installed kubelet drop-in at the CIS benchmark path"
fi

if [[ -d /var/lib/etcd ]]; then
  chmod 0700 /var/lib/etcd
  echo "hardened permissions: /var/lib/etcd"
fi

# These flags are safe for kubeadm static pods and close the automated CIS
# profiling findings without altering authentication or certificate trust.
inject_command_flag /etc/kubernetes/manifests/kube-apiserver.yaml \
  kube-apiserver --profiling=false
inject_command_flag /etc/kubernetes/manifests/kube-apiserver.yaml \
  kube-apiserver --service-account-extend-token-expiration=false
ensure_command_flag_value /etc/kubernetes/manifests/kube-apiserver.yaml \
  --audit-log-maxage= --audit-log-maxage=30
inject_command_flag /etc/kubernetes/manifests/kube-controller-manager.yaml \
  kube-controller-manager --profiling=false
inject_command_flag /etc/kubernetes/manifests/kube-scheduler.yaml \
  kube-scheduler --profiling=false

echo "CIS node hardening complete"
