#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
namespace="${AIMS_NAMESPACE:-production}"

for binary in kubectl helm jq; do
  command -v "$binary" >/dev/null || { echo "Missing required command: $binary" >&2; exit 1; }
done

required_crds=(
  clusters.postgresql.cnpg.io
  kafkas.kafka.strimzi.io
  rabbitmqclusters.rabbitmq.com
  redisreplications.redis.redis.opstreelabs.in
  tenants.minio.min.io
  rollouts.argoproj.io
  clusterpolicies.kyverno.io
  certificates.cert-manager.io
  gateways.gateway.networking.k8s.io
)
for crd in "${required_crds[@]}"; do
  kubectl get crd "$crd" >/dev/null || { echo "Missing operator CRD: $crd" >&2; exit 1; }
done

kubectl apply --server-side --force-conflicts -f "$root/platform/00-namespace.yaml"
kubectl get ns istio-ingress >/dev/null
kubectl apply --server-side --force-conflicts -f "$root/platform/00-foundation.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/05-rbac.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/15-external-secrets.yaml"

store_ready="$(kubectl get clustersecretstore vault -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')"
[[ "$store_ready" == True ]] || { echo "Vault ClusterSecretStore is not Ready" >&2; exit 1; }

# The Tenant asks the MinIO Operator to register a scrape configuration. Point
# it at the actual kube-prometheus-stack CR before reconciling the Tenant.
helm upgrade --install minio-operator minio-operator/operator --version 7.1.1 \
  --namespace minio-operator --create-namespace --reuse-values \
  -f "$root/platform/minio-operator-values.yaml" --history-max 10
kubectl -n minio-operator rollout status deployment/minio-operator --timeout=3m

kubectl apply --server-side --force-conflicts -f "$root/platform/10-data-messaging.yaml"

helm upgrade gatekeeper gatekeeper/gatekeeper --version 3.23.0 \
  --namespace gatekeeper-system --reuse-values --force-conflicts \
  -f "$root/platform/gatekeeper-values.yaml"

helm upgrade --install trivy-operator aqua/trivy-operator --version 0.34.0 \
  --namespace trivy-system --create-namespace \
  -f "$root/platform/trivy-operator-values.yaml" --history-max 10

kubectl apply --server-side --force-conflicts -f "$root/platform/20-policy-security.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/22-supply-chain-policy.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/25-kube-bench.yaml"

for _ in $(seq 1 40); do
  [[ "$(kubectl get constrainttemplate k8srequiredruntimehardening -o jsonpath='{.status.created}' 2>/dev/null)" == true ]] && break
  sleep 3
done
kubectl apply --server-side --force-conflicts -f "$root/platform/21-gatekeeper-constraint.yaml"

kubectl apply --server-side --force-conflicts -f "$root/platform/30-observability.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/50-backup.yaml"
kubectl apply --server-side --force-conflicts -f "$root/platform/60-backup-schedule.yaml"

helm upgrade --install loki grafana/loki --version 7.1.0 \
  --namespace observability --create-namespace -f "$root/platform/loki-values.yaml"
helm upgrade --install tempo grafana/tempo --version 1.24.4 \
  --namespace observability --create-namespace -f "$root/platform/tempo-values.yaml"
helm upgrade --install opensearch opensearch/opensearch --version 3.7.0 \
  --namespace opensearch --create-namespace -f "$root/platform/opensearch-values.yaml"

# Adopt the legacy frontend objects once so Helm can manage the complete web
# tier without deleting a healthy Deployment during the migration.
for object in service/aims-frontend deployment/aims-frontend poddisruptionbudget/aims-frontend; do
  if kubectl -n "$namespace" get "$object" >/dev/null 2>&1; then
    kubectl -n "$namespace" annotate "$object" \
      meta.helm.sh/release-name=aims \
      meta.helm.sh/release-namespace="$namespace" --overwrite
    kubectl -n "$namespace" label "$object" app.kubernetes.io/managed-by=Helm --overwrite
  fi
done
helm upgrade --install aims "$root/aims-chart" --namespace "$namespace" \
  --history-max 5 --force-conflicts

"$root/scripts/cleanup-production-legacy.sh"
kubectl delete clusterpolicy production-restricted-audit --ignore-not-found
kubectl -n production rollout restart deployment/aims-waypoint
kubectl -n production rollout status deployment/aims-waypoint --timeout=5m
kubectl -n production rollout status deployment/aims-frontend --timeout=5m
kubectl apply --server-side --force-conflicts -f "$root/platform/40-production-enforcement.yaml"
kubectl apply --server-side --force-conflicts -f "$root/cks-lab/00-lab-guardrails.yaml"

echo "Desired state applied. Run: $root/scripts/verify-aims.sh"
