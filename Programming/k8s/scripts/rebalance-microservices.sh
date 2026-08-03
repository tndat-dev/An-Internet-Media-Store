#!/usr/bin/env bash
set -euo pipefail

# Default is read-only. Set APPLY=true to evict one pod at a time until the
# aggregate AIMS microservice count is equal across all worker nodes.
NAMESPACE=${NAMESPACE:-production}
SELECTOR=${SELECTOR:-aims.hust.vn/workload-group=microservices}
APPLY=${APPLY:-false}

mapfile -t nodes < <(kubectl get nodes -l '!node-role.kubernetes.io/control-plane' \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | sort)
test "${#nodes[@]}" -gt 0

pod_json=$(kubectl -n "${NAMESPACE}" get pods -l "${SELECTOR}" -o json)
total=$(jq '[.items[] | select(.metadata.deletionTimestamp == null)] | length' \
  <<<"${pod_json}")
target=$((total / ${#nodes[@]}))

show_counts() {
  kubectl -n "${NAMESPACE}" get pods -l "${SELECTOR}" -o json | \
    jq -r '.items[] | select(.metadata.deletionTimestamp == null) | .spec.nodeName' | \
    sort | uniq -c
}

echo "workers=${#nodes[@]} pods=${total} target_per_worker=${target}"
show_counts
if [[ "${APPLY}" != "true" ]]; then
  echo "Read-only mode. Re-run with APPLY=true to rebalance."
  exit 0
fi

for _ in $(seq 1 "${total}"); do
  pod_json=$(kubectl -n "${NAMESPACE}" get pods -l "${SELECTOR}" -o json)
  over=$(jq -r --argjson target "${target}" '
    [.items[] | select(.metadata.deletionTimestamp == null) | .spec.nodeName]
    | group_by(.) | map({node: .[0], count: length})
    | map(select(.count > $target)) | sort_by(-.count) | .[0].node // empty' \
    <<<"${pod_json}")
  under=$(for node in "${nodes[@]}"; do
    count=$(jq -r --arg node "${node}" \
      '[.items[] | select(.metadata.deletionTimestamp == null and .spec.nodeName == $node)] | length' \
      <<<"${pod_json}")
    printf '%s\t%s\n' "${count}" "${node}"
  done | sort -n | head -n1 | cut -f2)

  [[ -z "${over}" ]] && break
  candidate=$(jq -r --arg over "${over}" --arg under "${under}" '
    .items as $all
    | $all[]
    | select(.metadata.deletionTimestamp == null and .spec.nodeName == $over)
    | .metadata.labels["app.kubernetes.io/name"] as $service
    | select([$all[] | select(.metadata.deletionTimestamp == null and
        .spec.nodeName == $under and
        .metadata.labels["app.kubernetes.io/name"] == $service)] | length == 0)
    | .metadata.name' <<<"${pod_json}" | head -n1)
  test -n "${candidate}"

  echo "Evicting ${candidate} from ${over}; preferred destination ${under}"
  kubectl -n "${NAMESPACE}" delete pod "${candidate}" --wait=false
  for _ in $(seq 1 90); do
    ready=$(kubectl -n "${NAMESPACE}" get pods -l "${SELECTOR}" -o json | \
      jq '[.items[] | select(.metadata.deletionTimestamp == null and
        .status.containerStatuses[0].ready == true)] | length')
    [[ "${ready}" -eq "${total}" ]] && break
    sleep 2
  done
done

show_counts

