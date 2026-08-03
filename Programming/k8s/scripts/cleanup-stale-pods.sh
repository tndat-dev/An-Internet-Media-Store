#!/usr/bin/env bash
set -euo pipefail

prune_known_tests=false
[[ ${1:-} == --prune-known-tests ]] && prune_known_tests=true

# Historical ReplicaSet pods can remain as Failed/Completed after a node reboot.
# Removing these records is safe: current controllers already own replacement
# replicas. Job pods are retained because their logs are audit evidence.
mapfile -t stale_pods < <(
  kubectl get pods -A -o json | jq -r '
    .items[] |
    select(.status.phase == "Failed" or .status.phase == "Succeeded") |
    select(.metadata.ownerReferences[0].kind == "ReplicaSet") |
    [.metadata.namespace, .metadata.name] | @tsv'
)

echo "stale ReplicaSet pods to delete: ${#stale_pods[@]}"
for entry in "${stale_pods[@]}"; do
  IFS=$'\t' read -r namespace pod <<< "$entry"
  kubectl -n "$namespace" delete pod "$pod" --wait=false
done

if $prune_known_tests; then
  # These are lab/load generators outside the declared AIMS desired state.
  kubectl -n default delete deployment postgres --ignore-not-found
  kubectl -n default delete service postgres --ignore-not-found
  kubectl -n default delete deployment postgres-loadgen --ignore-not-found
  kubectl -n production delete deployment loadgen nginx redis redis-loadgen --ignore-not-found
  kubectl -n production delete service nginx redis --ignore-not-found
  kubectl -n default delete gateway bookinfo-gateway --ignore-not-found
  kubectl -n default delete httproute bookinfo reviews-route --ignore-not-found
fi

# Temporary Kafka diagnostics created by the AIMS runbook never own state.
kubectl -n production delete pod aims-kafka-admin aims-kafka-smoke --ignore-not-found --wait=false

echo "cleanup complete"
