#!/usr/bin/env bash
set -euo pipefail

policy_source=${1:-/tmp/aims-audit-policy.yaml}
manifest=/etc/kubernetes/manifests/kube-apiserver.yaml
policy_target=/etc/kubernetes/audit-policy.yaml
log_dir=/var/log/kubernetes/audit
backup_pointer=/var/lib/aims-audit-last-backup
backup_dir=/var/backups/kubernetes

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
if [[ $policy_source == --rollback ]]; then
  [[ -s "$backup_pointer" ]] || { echo "no audit rollback pointer" >&2; exit 1; }
  backup=$(<"$backup_pointer")
  [[ -f "$backup" ]] || { echo "rollback manifest missing: $backup" >&2; exit 1; }
  cp -a "$backup" "$manifest"
  echo "restored $manifest from $backup"
  exit 0
fi
[[ -f "$policy_source" ]] || { echo "missing policy: $policy_source" >&2; exit 1; }
[[ -f "$manifest" ]] || { echo "missing kube-apiserver manifest" >&2; exit 1; }

install -d -m 0750 "$log_dir"
install -m 0640 "$policy_source" "$policy_target"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0700 "$backup_dir"
backup="${backup_dir}/kube-apiserver.yaml.pre-audit-${timestamp}"
cp -a "$manifest" "$backup"
printf '%s\n' "$backup" > "$backup_pointer"

tmp=$(mktemp)
awk '
  /- kube-apiserver$/ {
    print
    if (!flags) {
      print "    - --audit-policy-file=/etc/kubernetes/audit-policy.yaml"
      print "    - --audit-log-path=/var/log/kubernetes/audit/audit.log"
      print "    - --audit-log-format=json"
      print "    - --audit-log-maxage=30"
      print "    - --audit-log-maxbackup=10"
      print "    - --audit-log-maxsize=100"
      flags=1
    }
    next
  }
  /^    volumeMounts:$/ {
    print
    if (!mounts) {
      print "    - mountPath: /etc/kubernetes/audit-policy.yaml"
      print "      name: audit-policy"
      print "      readOnly: true"
      print "    - mountPath: /var/log/kubernetes/audit"
      print "      name: audit-log"
      mounts=1
    }
    next
  }
  /^  volumes:$/ {
    print
    if (!volumes) {
      print "  - hostPath:"
      print "      path: /etc/kubernetes/audit-policy.yaml"
      print "      type: File"
      print "    name: audit-policy"
      print "  - hostPath:"
      print "      path: /var/log/kubernetes/audit"
      print "      type: DirectoryOrCreate"
      print "    name: audit-log"
      volumes=1
    }
    next
  }
  {print}
' "$manifest" > "$tmp"

# If audit configuration already existed, restore the original and only refresh
# the policy file. This keeps the script idempotent.
if grep -q -- '--audit-policy-file=' "$manifest"; then
  rm -f "$tmp"
  echo "audit flags already present; policy refreshed"
  exit 0
fi

for required in --audit-policy-file= 'name: audit-policy' 'name: audit-log'; do
  grep -q -- "$required" "$tmp" || { echo "failed to inject $required" >&2; rm -f "$tmp"; exit 1; }
done

install -m 0600 "$tmp" "$manifest"
rm -f "$tmp"
echo "audit logging configured; rollback copy: $backup"
