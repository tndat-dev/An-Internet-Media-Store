#!/usr/bin/env bash
set -euo pipefail

# Safe DR exercise: restore only ConfigMaps from production into a new,
# disposable namespace. This deliberately excludes Secrets, workloads and PVCs.
backup_name=${BACKUP_NAME:-production-post-cks-20260801}
target_namespace=${TARGET_NAMESPACE:-production-drill}
restore_name=${RESTORE_NAME:-aims-config-drill-$(date -u +%Y%m%d%H%M%S)}
keep_namespace=${KEEP_NAMESPACE:-false}

case "${target_namespace}" in
  production|default|kube-system|velero)
    printf 'Refusing unsafe restore target namespace: %s\n' "${target_namespace}" >&2
    exit 1
    ;;
esac

if kubectl get namespace "${target_namespace}" >/dev/null 2>&1; then
  printf 'Refusing to use pre-existing namespace %s; choose a disposable namespace\n' \
    "${target_namespace}" >&2
  exit 1
fi

backup_json=$(kubectl -n velero get backups.velero.io "${backup_name}" -o json)
backup_phase=$(jq -r '.status.phase // ""' <<<"${backup_json}")
if [[ "${backup_phase}" != "Completed" ]]; then
  printf 'Backup %s is not usable: phase=%s\n' "${backup_name}" "${backup_phase:-unknown}" >&2
  exit 1
fi

kubectl create namespace "${target_namespace}"
kubectl label namespace "${target_namespace}" --overwrite \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/audit-version=latest \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/warn-version=latest \
  aims.hust.vn/purpose=restore-drill >/dev/null

kubectl -n velero create -f - <<EOF
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: ${restore_name}
  namespace: velero
  labels:
    app.kubernetes.io/part-of: aims
    restore.aims.io/type: configmap-drill
spec:
  backupName: ${backup_name}
  includedNamespaces:
    - production
  namespaceMapping:
    production: ${target_namespace}
  includedResources:
    - configmaps
  includeClusterResources: false
  restorePVs: false
  existingResourcePolicy: none
EOF

phase=""
for _ in $(seq 1 120); do
  restore_json=$(kubectl -n velero get restores.velero.io "${restore_name}" -o json 2>/dev/null || true)
  if [[ -n "${restore_json}" ]]; then
    phase=$(jq -r '.status.phase // ""' <<<"${restore_json}")
  else
    phase=""
  fi
  printf 'Restore %s phase=%s\n' "${restore_name}" "${phase:-Pending}"
  case "${phase}" in
    Completed)
      break
      ;;
    Failed|PartiallyFailed|FailedValidation)
      kubectl -n velero describe restores.velero.io "${restore_name}"
      printf 'Namespace %s retained for failure inspection\n' "${target_namespace}" >&2
      exit 1
      ;;
  esac
  sleep 5
done

if [[ "${phase}" != "Completed" ]]; then
  printf 'Timed out waiting for restore %s; namespace %s retained\n' \
    "${restore_name}" "${target_namespace}" >&2
  exit 1
fi

configmap_count=$(kubectl -n "${target_namespace}" get configmap --no-headers 2>/dev/null | wc -l)
pod_count=$(kubectl -n "${target_namespace}" get pod --no-headers 2>/dev/null | wc -l)
secret_count=$(kubectl -n "${target_namespace}" get secret --no-headers 2>/dev/null | wc -l)
pvc_count=$(kubectl -n "${target_namespace}" get pvc --no-headers 2>/dev/null | wc -l)
controller_count=$(kubectl -n "${target_namespace}" get deployment,statefulset,daemonset,job,cronjob \
  --no-headers 2>/dev/null | wc -l)

if (( configmap_count == 0 )); then
  printf 'Restore completed but no ConfigMaps were restored\n' >&2
  exit 1
fi

if (( pod_count != 0 || secret_count != 0 || pvc_count != 0 || controller_count != 0 )); then
  printf 'Isolation check failed: pods=%s secrets=%s pvcs=%s controllers=%s\n' \
    "${pod_count}" "${secret_count}" "${pvc_count}" "${controller_count}" >&2
  printf 'Namespace %s retained for inspection\n' "${target_namespace}" >&2
  exit 1
fi

printf 'PASS restore=%s backup=%s configmaps=%s pods=0 secrets=0 pvcs=0 controllers=0\n' \
  "${restore_name}" "${backup_name}" "${configmap_count}"

if [[ "${keep_namespace}" == "true" ]]; then
  printf 'Namespace %s retained because KEEP_NAMESPACE=true\n' "${target_namespace}"
  exit 0
fi

kubectl delete namespace "${target_namespace}" --wait=false >/dev/null
for _ in $(seq 1 120); do
  if ! kubectl get namespace "${target_namespace}" >/dev/null 2>&1; then
    printf 'Cleanup complete: namespace %s deleted; Restore CR retained as evidence\n' \
      "${target_namespace}"
    exit 0
  fi
  sleep 2
done

printf 'Timed out deleting namespace %s\n' "${target_namespace}" >&2
exit 1
