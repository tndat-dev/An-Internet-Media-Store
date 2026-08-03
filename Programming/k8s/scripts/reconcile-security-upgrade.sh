#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
configure_audit=${CONFIGURE_AUDIT:-true}

for binary in kubectl helm jq; do
  command -v "$binary" >/dev/null || { echo "missing required command: $binary" >&2; exit 1; }
done

kubectl get --raw=/readyz >/dev/null

echo "server-side validation"
for manifest in \
  "$root/platform/00-namespace.yaml" \
  "$root/platform/00-foundation.yaml" \
  "$root/platform/05-rbac.yaml" \
  "$root/platform/20-policy-security.yaml" \
  "$root/platform/22-supply-chain-policy.yaml" \
  "$root/platform/25-kube-bench.yaml" \
  "$root/platform/40-production-enforcement.yaml"; do
  kubectl apply --server-side --dry-run=server -f "$manifest" >/dev/null
done
kubectl apply --dry-run=client -f "$root/cks-lab/00-lab-guardrails.yaml" >/dev/null
helm lint "$root/aims-chart"
helm template aims "$root/aims-chart" --namespace production |
  kubectl apply --server-side --dry-run=server -f - >/dev/null

if [[ "$configure_audit" == true ]]; then
  "$root/scripts/configure-kube-apiserver-audit.sh"
fi

"$root/scripts/deploy-aims-resources.sh"

kubectl -n security-system rollout status ds/kube-bench-control-plane --timeout=10m
kubectl -n security-system rollout status ds/kube-bench-worker --timeout=10m

for _ in $(seq 1 120); do
  healthy=$(kubectl -n production get rollouts.argoproj.io -o json |
    jq '[.items[] | select(.status.phase == "Healthy" and .status.availableReplicas == .spec.replicas)] | length')
  [[ "$healthy" == 9 ]] && break
  sleep 5
done
[[ $(kubectl -n production get rollouts.argoproj.io -o json |
  jq '[.items[] | select(.status.phase == "Healthy" and .status.availableReplicas == .spec.replicas)] | length') == 9 ]]

"$root/scripts/cleanup-stale-pods.sh" --prune-known-tests
"$root/scripts/verify-aims.sh"
"$root/scripts/verify-cks-lab.sh"

echo "security upgrade reconciled and verified"
