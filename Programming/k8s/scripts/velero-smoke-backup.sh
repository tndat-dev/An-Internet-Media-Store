#!/usr/bin/env bash
set -euo pipefail

backup_name="production-smoke-$(date -u +%Y%m%d%H%M%S)"

kubectl -n velero apply -f - <<EOF
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: ${backup_name}
  namespace: velero
  labels:
    app.kubernetes.io/part-of: aims
    backup.aims.io/tier: smoke
spec:
  includedNamespaces:
    - production
  storageLocation: default
  defaultVolumesToFsBackup: false
  snapshotVolumes: false
  ttl: 24h
EOF

for _ in $(seq 1 120); do
  phase="$(kubectl -n velero get backups.velero.io "${backup_name}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  case "${phase}" in
    Completed)
      echo "Backup ${backup_name} completed"
      exit 0
      ;;
    Failed|PartiallyFailed|FailedValidation)
      kubectl -n velero describe backups.velero.io "${backup_name}"
      exit 1
      ;;
  esac
  sleep 5
done

echo "Timed out waiting for backup ${backup_name}" >&2
exit 1
