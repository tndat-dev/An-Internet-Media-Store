#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/00-namespace.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/00-foundation.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/05-rbac.yaml"
helm upgrade --install minio-operator minio-operator/operator --version 7.1.1 \
  --namespace minio-operator --create-namespace --reuse-values \
  -f "${ROOT_DIR}/platform/minio-operator-values.yaml" --history-max 10
kubectl -n minio-operator rollout status deployment/minio-operator --timeout=3m
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/10-data-messaging.yaml"
kubectl apply -f "${ROOT_DIR}/platform/15-external-secrets.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/20-policy-security.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/22-supply-chain-policy.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/25-kube-bench.yaml"

helm upgrade --install trivy-operator aqua/trivy-operator --version 0.34.0 \
  --namespace trivy-system --create-namespace \
  -f "${ROOT_DIR}/platform/trivy-operator-values.yaml" --history-max 10

for _ in $(seq 1 30); do
  [[ "$(kubectl get constrainttemplate k8srequiredruntimehardening \
    -o jsonpath='{.status.created}' 2>/dev/null)" == true ]] && break
  sleep 2
done
kubectl apply -f "${ROOT_DIR}/platform/21-gatekeeper-constraint.yaml"
kubectl apply -f "${ROOT_DIR}/platform/30-observability.yaml"
kubectl apply -f "${ROOT_DIR}/platform/50-backup.yaml"
kubectl apply -f "${ROOT_DIR}/platform/60-backup-schedule.yaml"

for object in service/aims-frontend deployment/aims-frontend poddisruptionbudget/aims-frontend; do
  if kubectl -n production get "$object" >/dev/null 2>&1; then
    kubectl -n production annotate "$object" \
      meta.helm.sh/release-name=aims \
      meta.helm.sh/release-namespace=production --overwrite
    kubectl -n production label "$object" app.kubernetes.io/managed-by=Helm --overwrite
  fi
done
helm upgrade --install aims "${ROOT_DIR}/aims-chart" \
  --namespace production --create-namespace=false --history-max 10 --force-conflicts

"${ROOT_DIR}/scripts/cleanup-production-legacy.sh"
kubectl delete clusterpolicy production-restricted-audit --ignore-not-found
kubectl -n production rollout restart deployment/aims-waypoint
kubectl -n production rollout status deployment/aims-waypoint --timeout=5m
kubectl -n production rollout status deployment/aims-frontend --timeout=5m
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/platform/40-production-enforcement.yaml"
kubectl apply --server-side --force-conflicts -f "${ROOT_DIR}/cks-lab/00-lab-guardrails.yaml"

echo "AIMS resources reconciled. Run scripts/verify-aims.sh after operators settle."
