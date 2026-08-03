#!/usr/bin/env bash
set -euo pipefail

backup_name=${BACKUP_NAME:-production-final-$(date -u +%Y%m%d%H%M%S)}

kubectl -n velero apply -f - <<EOF
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: ${backup_name}
  namespace: velero
  labels:
    app.kubernetes.io/part-of: aims
    backup.aims.io/tier: final-validation
spec:
  includedNamespaces:
    - production
  excludedNamespaceScopedResources:
    - volumesnapshots.snapshot.storage.k8s.io
  excludedClusterScopedResources:
    - volumesnapshotcontents.snapshot.storage.k8s.io
  storageLocation: default
  defaultVolumesToFsBackup: true
  snapshotVolumes: false
  ttl: 720h
EOF

for _ in $(seq 1 180); do
  status=$(kubectl -n velero get backups.velero.io "${backup_name}" -o json 2>/dev/null || true)
  phase=$(jq -r '.status.phase // ""' <<<"${status}")
  progress=$(jq -r '(.status.progress.itemsBackedUp // 0 | tostring) + "/" + (.status.progress.totalItems // 0 | tostring)' <<<"${status}")
  printf 'Backup %s phase=%s progress=%s\n' "${backup_name}" "${phase:-Pending}" "${progress}"
  case "${phase}" in
    Completed)
      errors=$(jq -r '.status.errors // 0' <<<"${status}")
      warnings=$(jq -r '.status.warnings // 0' <<<"${status}")
      printf 'PASS backup=%s errors=%s warnings=%s items=%s\n' \
        "${backup_name}" "${errors}" "${warnings}" "${progress}"
      exit 0
      ;;
    Failed|PartiallyFailed|FailedValidation)
      kubectl -n velero describe backups.velero.io "${backup_name}"
      exit 1
      ;;
  esac
  sleep 10
done

printf 'Timed out waiting for backup %s\n' "${backup_name}" >&2
exit 1
