#!/usr/bin/env bash
set -euo pipefail

# Remove only known stateless lab/legacy controllers. Stateful PVCs and all
# current operator-managed AIMS resources are intentionally left untouched.
namespace=production

kubectl -n "$namespace" delete deployment \
  aims-backend aims-traffic shop-frontend shop-loadgen --ignore-not-found
kubectl -n "$namespace" delete statefulset aims-postgres --ignore-not-found
kubectl -n "$namespace" delete service \
  aims-backend aims-postgres shop-frontend --ignore-not-found
kubectl -n "$namespace" delete configmap shop-app --ignore-not-found

if kubectl get validatingadmissionpolicybinding sentinel-experiment-resource-lock >/dev/null 2>&1; then
  echo "Sentinel validation lock is active; preserving nginx/redis/load generators."
else
  kubectl -n "$namespace" delete deployment \
    loadgen nginx redis redis-loadgen --ignore-not-found
  kubectl -n "$namespace" delete service nginx redis --ignore-not-found
  kubectl -n "$namespace" delete configmap nginx-runtime-config --ignore-not-found
fi
kubectl -n "$namespace" delete poddisruptionbudget aims-backend --ignore-not-found
kubectl -n "$namespace" delete gateway.networking.istio.io aims-gateway --ignore-not-found
kubectl -n "$namespace" delete virtualservice.networking.istio.io aims-web --ignore-not-found
kubectl -n "$namespace" delete ciliumnetworkpolicy \
  quarantine-nginx-56fcf95486-lhs5s --ignore-not-found

echo "Known production lab/legacy resources removed; PVCs were preserved."
