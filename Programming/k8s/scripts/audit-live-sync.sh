#!/usr/bin/env bash
set -euo pipefail

# Read-only audit for the production-like AIMS cluster. Run this script on a
# control-plane host whose kubeconfig can read every namespace.
NAMESPACE=${NAMESPACE:-production}
EXPECTED_REVISION=${EXPECTED_REVISION:-}
FULL_VERIFY=${FULL_VERIFY:-true}
SHOW_KUBECTL_DIFF=${SHOW_KUBECTL_DIFF:-false}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
k8s_root=$(cd -- "${script_dir}/.." && pwd)
failures=0

check() {
  local label=$1 actual=$2 expected=$3
  if [[ "${actual}" == "${expected}" ]]; then
    printf 'PASS %-44s %s\n' "${label}" "${actual}"
  else
    printf 'FAIL %-44s actual=%s expected=%s\n' \
      "${label}" "${actual:-<empty>}" "${expected}"
    failures=$((failures + 1))
  fi
}

nodes=$(kubectl get nodes -o json)
pods=$(kubectl get pods -A -o json)
jobs=$(kubectl get jobs -A -o json)
pvcs=$(kubectl get pvc -A -o json)

check "all nodes Ready" \
  "$(jq '[.items[] | select(any(.status.conditions[]; .type == "Ready" and .status == "True"))] | length' <<<"${nodes}")" \
  "$(jq '.items | length' <<<"${nodes}")"
check "nodes without DiskPressure" \
  "$(jq '[.items[] | select(any(.status.conditions[]; .type == "DiskPressure" and .status == "False"))] | length' <<<"${nodes}")" \
  "$(jq '.items | length' <<<"${nodes}")"

bad_pods=$(jq '[
  .items[]
  | select(.metadata.deletionTimestamp == null)
  | select(.status.phase != "Succeeded")
  | select(
      .status.phase != "Running"
      or ((.status.containerStatuses // []) | length) == 0
      or any(.status.containerStatuses[]?; .ready != true)
    )
] | length' <<<"${pods}")
check "non-running or non-ready pods" "${bad_pods}" 0

failed_jobs=$(jq '[
  .items[]
  | select((.status.failed // 0) > 0)
  | select(([.status.conditions[]? | select(.type == "Complete" and .status == "True")] | length) == 0)
] | length' <<<"${jobs}")
check "currently failed Jobs" "${failed_jobs}" 0
check "unbound PVCs" \
  "$(jq '[.items[] | select(.status.phase != "Bound")] | length' <<<"${pvcs}")" 0

check "Argo CD sync" \
  "$(kubectl -n argocd get application aims-production -o jsonpath='{.status.sync.status}')" Synced
check "Argo CD health" \
  "$(kubectl -n argocd get application aims-production -o jsonpath='{.status.health.status}')" Healthy

live_revision=$(kubectl -n argocd get application aims-production \
  -o jsonpath='{.status.sync.revision}')
printf 'INFO %-44s %s\n' "Argo CD live revision" "${live_revision}"
if [[ -n "${EXPECTED_REVISION}" ]]; then
  check "Argo CD expected revision" "${live_revision}" "${EXPECTED_REVISION}"
fi

check "AIMS Rollouts available replicas" \
  "$(kubectl -n "${NAMESPACE}" get rollouts.argoproj.io -l app.kubernetes.io/part-of=aims -o json | jq '[.items[] | select(.spec.replicas == .status.availableReplicas)] | length')" 9
check "AIMS ready microservice pods" \
  "$(kubectl -n "${NAMESPACE}" get pods -l aims.hust.vn/workload-group=microservices -o json | jq '[.items[] | select(.metadata.deletionTimestamp == null and .status.phase == "Running" and any(.status.containerStatuses[]?; .ready == true))] | length')" 18
check "CloudNativePG ready instances" \
  "$(kubectl -n "${NAMESPACE}" get cluster.postgresql.cnpg.io aims-postgres-cnpg -o jsonpath='{.status.readyInstances}')" 3
check "Kafka Ready" \
  "$(kubectl -n "${NAMESPACE}" get kafka.kafka.strimzi.io aims-kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True
check "RabbitMQ all replicas Ready" \
  "$(kubectl -n "${NAMESPACE}" get rabbitmqcluster.rabbitmq.com aims-rabbitmq -o jsonpath='{.status.conditions[?(@.type=="AllReplicasReady")].status}')" True
check "MinIO health" \
  "$(kubectl -n "${NAMESPACE}" get tenant.minio.min.io aims-minio -o jsonpath='{.status.healthStatus}')" green
check "OpenSearch ready replicas" \
  "$(kubectl -n opensearch get statefulset aims-security-master -o jsonpath='{.status.readyReplicas}')" 3
check "Vault ready replicas" \
  "$(kubectl -n vault get statefulset vault -o jsonpath='{.status.readyReplicas}')" 3
check "Longhorn healthy volumes" \
  "$(kubectl -n longhorn-system get volumes.longhorn.io -o json | jq '[.items[] | select(.status.robustness == "healthy")] | length')" \
  "$(kubectl -n longhorn-system get volumes.longhorn.io -o json | jq '.items | length')"

if [[ "${SHOW_KUBECTL_DIFF}" == "true" ]]; then
  echo "INFO kubectl diff returns 1 when an operator/defaulting field differs."
  manifests=(
    platform/00-foundation.yaml
    platform/05-rbac.yaml
    platform/10-data-messaging.yaml
    platform/15-external-secrets.yaml
    platform/20-policy-security.yaml
    platform/21-gatekeeper-constraint.yaml
    platform/22-supply-chain-policy.yaml
    platform/25-kube-bench.yaml
    platform/30-observability.yaml
    platform/40-production-enforcement.yaml
    platform/50-backup.yaml
    platform/60-backup-schedule.yaml
    platform/argocd-application.yaml
    cks-lab/00-lab-guardrails.yaml
  )
  for manifest in "${manifests[@]}"; do
    set +e
    kubectl diff --server-side -f "${k8s_root}/${manifest}" >/dev/null
    result=$?
    set -e
    if ((result > 1)); then
      printf 'FAIL kubectl diff error: %s (exit %s)\n' "${manifest}" "${result}"
      failures=$((failures + 1))
    else
      printf 'INFO kubectl diff %-31s exit=%s\n' "${manifest}" "${result}"
    fi
  done
fi

if [[ "${FULL_VERIFY}" == "true" ]]; then
  "${script_dir}/verify-aims.sh"
  "${script_dir}/verify-cks-lab.sh"
fi

if ((failures > 0)); then
  printf 'AUDIT FAIL: %s assertion(s) failed\n' "${failures}" >&2
  exit 1
fi
echo "AUDIT PASS: desired revision and live AIMS resources are healthy"
