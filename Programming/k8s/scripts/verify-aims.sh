#!/usr/bin/env bash
set -euo pipefail

failures=0
check() {
  local label=$1 actual=$2 expected=$3
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS  %-42s %s\n' "$label" "$actual"
  else
    printf 'FAIL  %-42s actual=%s expected=%s\n' "$label" "$actual" "$expected"
    failures=$((failures + 1))
  fi
}

expected_nodes=${EXPECTED_READY_NODES:-6}
expected_control_planes=${EXPECTED_CONTROL_PLANES:-3}
expected_workers=${EXPECTED_WORKERS:-3}
expected_source_revision=${EXPECTED_SOURCE_REVISION:-}
expected_notification_source_revision=${EXPECTED_NOTIFICATION_SOURCE_REVISION:-}
expected_inventory_source_revision=${EXPECTED_INVENTORY_SOURCE_REVISION:-}

nodes=$(kubectl get nodes -o json)
ready_nodes=$(jq '[.items[] | select(.status.conditions[] | .type == "Ready" and .status == "True")] | length' <<< "$nodes")
check "Ready nodes" "$ready_nodes" "$expected_nodes"
check "Control-plane nodes" "$(jq '[.items[] | select(.metadata.labels["node-role.kubernetes.io/control-plane"] != null)] | length' <<< "$nodes")" "$expected_control_planes"
check "Worker nodes" "$(jq '[.items[] | select(.metadata.labels["node-role.kubernetes.io/control-plane"] == null)] | length' <<< "$nodes")" "$expected_workers"
check "Nodes without DiskPressure" "$(jq '[.items[] | select(.status.conditions[] | .type == "DiskPressure" and .status == "False")] | length' <<< "$nodes")" "$expected_nodes"
check "Production PSA Restricted Enforce" "$(kubectl get ns production -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')" restricted

all_pods=$(kubectl get pods -A -o json)
check "Cluster problem/Unknown pods" "$(jq '[.items[] | select((.status.phase != "Running" and .status.phase != "Succeeded") or (.status.phase == "Running" and any(.status.containerStatuses[]?; .ready != true)))] | length' <<< "$all_pods")" 0
controllers=$(kubectl get deployment,statefulset,daemonset -A -o json)
check "Incomplete cluster controllers" "$(jq '[.items[] | select(if .kind == "DaemonSet" then ((.status.numberReady // 0) != (.status.desiredNumberScheduled // 0)) else ((.status.readyReplicas // 0) != (.spec.replicas // 0)) end)] | length' <<< "$controllers")" 0
check "Unbound PVCs" "$(kubectl get pvc -A -o json | jq '[.items[] | select(.status.phase != "Bound")] | length')" 0

check "Jenkins namespace PSA Restricted" "$(kubectl get namespace jenkins -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')" restricted
check "Jenkins controller Ready" "$(kubectl -n jenkins get statefulset aims-jenkins -o jsonpath='{.status.readyReplicas}')" 1
check "Jenkins PVC Bound" "$(kubectl -n jenkins get pvc aims-jenkins -o jsonpath='{.status.phase}')" Bound
jenkins_controller_can_create=$(kubectl -n jenkins auth can-i create pods \
  --as=system:serviceaccount:jenkins:aims-jenkins-controller 2>/dev/null || true)
jenkins_controller_can_read_secrets=$(kubectl -n jenkins auth can-i get secrets \
  --as=system:serviceaccount:jenkins:aims-jenkins-controller 2>/dev/null || true)
check "Jenkins controller can create agents" "${jenkins_controller_can_create}" yes
check "Jenkins controller cannot read Secrets" "${jenkins_controller_can_read_secrets}" no

rollouts=$(kubectl -n production get rollouts.argoproj.io -o json)
check "Healthy AIMS Rollouts" "$(jq '[.items[] | select(.status.phase == "Healthy" and .status.availableReplicas == .spec.replicas)] | length' <<< "$rollouts")" 10

pods=$(kubectl -n production get pods -l aims.hust.vn/workload-group=microservices -o json)
check "Ready microservice pods" "$(jq '[.items[] | select(.metadata.deletionTimestamp == null and .status.containerStatuses[0].ready == true)] | length' <<< "$pods")" 20

if [[ -n "${expected_source_revision}" ]]; then
  check "Independent services source revision" \
    "$(jq --arg revision "${expected_source_revision}" '[.items[] | select(.metadata.deletionTimestamp == null and .metadata.annotations["aims.hust.vn/source-revision"] == $revision)] | length' <<< "$pods")" 20
fi
if [[ -n "${expected_notification_source_revision}" ]]; then
  check "Notification service source revision" \
    "$(jq --arg revision "${expected_notification_source_revision}" '[.items[] | select(.metadata.deletionTimestamp == null and .metadata.labels["app.kubernetes.io/name"] == "notification-service" and .metadata.annotations["aims.hust.vn/source-revision"] == $revision)] | length' <<< "$pods")" 2
fi
if [[ -n "${expected_inventory_source_revision}" ]]; then
  check "Inventory service source revision" \
    "$(jq --arg revision "${expected_inventory_source_revision}" '[.items[] | select(.metadata.deletionTimestamp == null and .metadata.labels["app.kubernetes.io/name"] == "inventory-service" and .metadata.annotations["aims.hust.vn/source-revision"] == $revision)] | length' <<< "$pods")" 2
fi

frontend=$(kubectl -n production get deployment aims-frontend -o json)
check "Ready frontend replicas" "$(jq -r '.status.readyReplicas // 0' <<< "$frontend")" 2
check "Frontend managed by Helm" "$(jq -r '.metadata.labels["app.kubernetes.io/managed-by"] // ""' <<< "$frontend")" Helm
check "Frontend runs non-root" "$(jq -r '.spec.template.spec.securityContext.runAsNonRoot' <<< "$frontend")" true
check "Frontend read-only rootfs" "$(jq -r '.spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem' <<< "$frontend")" true
frontend_pods=$(kubectl -n production get pods -l app=aims-frontend -o json)
check "Frontend replicas on distinct nodes" "$(jq '[.items[] | select(.metadata.deletionTimestamp == null and .status.containerStatuses[0].ready == true) | .spec.nodeName] | unique | length' <<< "$frontend_pods")" 2
if [[ -n "${expected_source_revision}" ]]; then
  check "Frontend source revision" \
    "$(jq --arg revision "${expected_source_revision}" '[.items[] | select(.metadata.deletionTimestamp == null and .metadata.annotations["aims.hust.vn/source-revision"] == $revision)] | length' <<< "$frontend_pods")" 2
fi

mapfile -t worker_names < <(jq -r '.items[] | select(.metadata.labels["node-role.kubernetes.io/control-plane"] == null) | .metadata.name' <<< "$nodes" | sort)
counts=()
for node in "${worker_names[@]}"; do
  count=$(jq --arg node "$node" '[.items[] | select(.metadata.deletionTimestamp == null and .spec.nodeName == $node)] | length' <<< "$pods")
  counts+=("$count")
  printf 'INFO  %-42s %s\n' "Microservices on $node" "$count"
done
min_count=$(printf '%s\n' "${counts[@]}" | sort -n | head -1)
max_count=$(printf '%s\n' "${counts[@]}" | sort -n | tail -1)
placement_ok=false
(( max_count - min_count <= 1 )) && placement_ok=true
check "Microservice placement max skew <= 1" "$placement_ok" true

check "CNPG ready instances" "$(kubectl -n production get cluster aims-postgres-cnpg -o jsonpath='{.status.readyInstances}')" 3
check "Redis replication master" "$(kubectl -n production get redisreplications.redis.redis.opstreelabs.in aims-redis -o jsonpath='{.status.masterNode}')" aims-redis-0
check "Kafka Ready" "$(kubectl -n production get kafka aims-kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True
check "Kafka topic CRs Ready" "$(kubectl -n production get kafkatopics.kafka.strimzi.io -l strimzi.io/cluster=aims-kafka -o json | jq '[.items[] | select(.status.conditions[] | .type == "Ready" and .status == "True")] | length')" 6
check "Versioned Kafka event topics Ready" "$(kubectl -n production get kafkatopics.kafka.strimzi.io -o json | jq '[.items[] | select(.metadata.name == "aims.business.order.created.v1" or .metadata.name == "aims.business.inventory.reserved.v1" or .metadata.name == "aims.business.inventory.rejected.v1" or .metadata.name == "aims.business.payment.completed.v1") | select(.status.conditions[] | .type == "Ready" and .status == "True")] | length')" 4
kafka_pods=$(kubectl -n production get pods -l strimzi.io/name=aims-kafka-kafka -o json)
check "Kafka brokers on distinct workers" "$(jq '[.items[] | select(.metadata.deletionTimestamp == null and .status.containerStatuses[0].ready == true) | .spec.nodeName] | unique | length' <<< "$kafka_pods")" 3
check "RabbitMQ all replicas" "$(kubectl -n production get rabbitmqcluster aims-rabbitmq -o jsonpath='{.status.conditions[?(@.type=="AllReplicasReady")].status}')" True
check "MinIO health" "$(kubectl -n production get tenant aims-minio -o jsonpath='{.status.healthStatus}')" green
check "MinIO excluded from recursive Kopia" "$(kubectl -n production get tenant aims-minio -o jsonpath='{.spec.pools[0].annotations.backup\.velero\.io/backup-volumes-excludes}')" data0,data1,cfg-vol
minio_pvcs=$(kubectl -n production get pvc -l v1.min.io/tenant=aims-minio -o json)
check "MinIO PVC count" "$(jq '.items | length' <<< "$minio_pvcs")" 4
check "MinIO PVCs expanded to 50Gi" "$(jq '[.items[] | select(.status.phase == "Bound" and .status.capacity.storage == "50Gi" and .spec.resources.requests.storage == "50Gi")] | length' <<< "$minio_pvcs")" 4
check "OpenSearch ready replicas" "$(kubectl -n opensearch get sts aims-security-master -o jsonpath='{.status.readyReplicas}')" 3
check "Vault secret store" "$(kubectl get clustersecretstore vault -o jsonpath='{.status.conditions[0].status}')" True
check "Velero BSL" "$(kubectl -n velero get backupstoragelocations.velero.io default -o jsonpath='{.status.phase}')" Available
backup_repo=$(kubectl -n velero get backuprepositories.velero.io production-default-kopia -o json)
check "Velero Kopia repository ready" "$(jq -r '.status.phase' <<< "$backup_repo")" Ready
check "Latest Kopia maintenance" "$(jq -r '.status.recentMaintenance | last | .result // "Missing"' <<< "$backup_repo")" Succeeded
check "Failed Kopia maintenance Jobs" "$(kubectl -n velero get jobs -o json | jq '[.items[] | select((.metadata.name | contains("kopia-maintain")) and ((.status.failed // 0) > 0))] | length')" 0
volume_backups=$(kubectl -n velero get podvolumebackups.velero.io -o json)
velero_backups=$(kubectl -n velero get backups.velero.io -o json)
stale_volume_backups=$(printf '%s\n%s\n' "$volume_backups" "$velero_backups" | jq -s '
  .[0] as $pvbs | .[1] as $backups |
  [ $pvbs.items[]
    | select(.status.phase == "InProgress" or .status.phase == "Prepared") as $pvb
    | $backups.items[]
    | select(.metadata.name == $pvb.metadata.labels["velero.io/backup-name"])
    | select(.status.phase == "Failed" or .status.phase == "PartiallyFailed"
        or .status.phase == "FailedValidation" or .status.phase == "Completed")
  ] | length')
check "Stale Kopia volume backups" "$stale_volume_backups" 0
check "Gatekeeper audit ready" "$(kubectl -n gatekeeper-system get deploy gatekeeper-audit -o jsonpath='{.status.readyReplicas}')" 1
check "Gatekeeper template created" "$(kubectl get constrainttemplate k8srequiredruntimehardening -o jsonpath='{.status.created}')" true
check "Gatekeeper runtime enforcement" "$(kubectl get k8srequiredruntimehardening production-runtime-hardening -o jsonpath='{.spec.enforcementAction}')" deny

check "Ambient-compatible microservice runtime" "$(jq '[.items[] | select(.spec.runtimeClassName == null)] | length' <<< "$pods")" 20
check "Independent signed service images" "$(jq '[.items[] | select(.spec.containers[0].image | test("^ghcr.io/tndat-dev/aims-(api-gateway|auth-service|catalog-service|cart-service|order-service|payment-service|inventory-service|notification-service|search-recommendation-service|security-telemetry-service)@sha256:"))] | length' <<< "$pods")" 20
check "Distinct microservice image repositories" "$(jq '[.items[].spec.containers[0].image | split("@")[0]] | unique | length' <<< "$pods")" 10
check "Localhost hardened telemetry pods" "$(jq '[.items[] | select(.metadata.labels["app.kubernetes.io/name"] == "security-telemetry-service" and .spec.securityContext.seccompProfile.type == "Localhost" and .spec.securityContext.appArmorProfile.type == "Localhost")] | length' <<< "$pods")" 2
check "Containers dropping ALL capabilities" "$(jq '[.items[].spec.containers[] | select((.securityContext.capabilities.drop // []) | index("ALL"))] | length' <<< "$pods")" 20
check "Microservice read-only rootfs" "$(jq '[.items[].spec.containers[] | select(.securityContext.readOnlyRootFilesystem == true)] | length' <<< "$pods")" 20

check "Gateway API ingress Programmed" "$(kubectl -n istio-ingress get gateway aims-ingress -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}')" True
check "Ambient waypoint Programmed" "$(kubectl -n production get gateway aims-waypoint -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}')" True
check "ztunnel node coverage" "$(kubectl -n istio-system get ds ztunnel -o jsonpath='{.status.numberReady}')" "$(kubectl -n istio-system get ds ztunnel -o jsonpath='{.status.desiredNumberScheduled}')"
check "AIMS HTTPRoute Accepted" "$(kubectl -n production get httproute aims-web -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}')" True
check "Ingress TLS certificate Ready" "$(kubectl -n istio-ingress get certificate aims-ingress-tls -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True
check "Gateway HTTPS listener Programmed" "$(kubectl -n istio-ingress get gateway aims-ingress -o json | jq -r '[.status.listeners[] | select(.name == "https") | .conditions[] | select(.type == "Programmed") | .status][0] // "False"')" True
gateway_ready=$(kubectl -n istio-ingress get deploy aims-ingress-istio -o jsonpath='{.status.readyReplicas}')
gateway_ha=false
(( ${gateway_ready:-0} >= 2 )) && gateway_ha=true
check "Istio ingress replicas >= 2" "$gateway_ha" true

# Conditions can remain healthy while a pre-reboot pod network namespace is
# stale. Sample both listeners repeatedly so a broken endpoint is observable.
ingress_node_ip=${AIMS_INGRESS_NODE_IP:-$(jq -r '.items[0].status.addresses[] | select(.type == "InternalIP") | .address' <<< "$nodes")}
ingress_service=$(kubectl -n istio-ingress get service aims-ingress-istio -o json)
http_node_port=$(jq -r '.spec.ports[] | select(.name == "http") | .nodePort' <<< "$ingress_service")
https_node_port=$(jq -r '.spec.ports[] | select(.name == "https") | .nodePort' <<< "$ingress_service")
gateway_samples=${AIMS_GATEWAY_SAMPLES:-6}
http_ok=0
https_ok=0
for _ in $(seq 1 "$gateway_samples"); do
  [[ "$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: aims.lab' \
    "http://${ingress_node_ip}:${http_node_port}/")" == "200" ]] && http_ok=$((http_ok + 1))
  [[ "$(curl -ksS -o /dev/null -w '%{http_code}' \
    --resolve "aims.lab:${https_node_port}:${ingress_node_ip}" \
    "https://aims.lab:${https_node_port}/")" == "200" ]] && https_ok=$((https_ok + 1))
done
check "Gateway HTTP samples" "$http_ok" "$gateway_samples"
check "Gateway HTTPS samples" "$https_ok" "$gateway_samples"
check "RBAC readonly role exists" "$(kubectl -n production get role aims-readonly -o jsonpath='{.metadata.name}')" aims-readonly
check "Kyverno Cosign/SLSA policy ready" "$(kubectl get clusterpolicy aims-verify-signed-slsa-images -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True
check "Kyverno Cosign/SLSA policy Enforce" "$(kubectl get clusterpolicy aims-verify-signed-slsa-images -o jsonpath='{.spec.validationFailureAction}')" Enforce
check "Kyverno admission can read GHCR credential" "$(kubectl auth can-i get secret/ghcr-pull -n production --as=system:serviceaccount:kyverno:kyverno-admission-controller)" yes
check "Kyverno background can read GHCR credential" "$(kubectl auth can-i get secret/ghcr-pull -n production --as=system:serviceaccount:kyverno:kyverno-background-controller)" yes
check "Kyverno AIMS runtime policy Enforce" "$(kubectl get clusterpolicy production-runtime-hardening -o jsonpath='{.spec.validationFailureAction}')" Enforce
check "Trivy Operator ready" "$(kubectl -n trivy-system get deploy trivy-operator -o jsonpath='{.status.readyReplicas}')" 1
check "Trivy server ready" "$(kubectl -n trivy-system get sts trivy-server -o jsonpath='{.status.readyReplicas}')" 1
check "Failed Trivy scan Jobs" "$(kubectl -n trivy-system get jobs -o json | jq '[.items[] | select((.status.failed // 0) > 0)] | length')" 0
trivy_cutoff=$(date -u -d '2 minutes ago' +%s)
check "Trivy scan pods Pending > 2m" "$(kubectl -n trivy-system get pods -o json | jq --argjson cutoff "$trivy_cutoff" '[.items[] | select(.status.phase == "Pending" and (.metadata.creationTimestamp | fromdateiso8601) < $cutoff)] | length')" 0
api_servers=$(kubectl -n kube-system get pods -l component=kube-apiserver -o json)
check "API servers with audit flags" "$(jq '[.items[] | select(any(.spec.containers[0].command[]; startswith("--audit-policy-file=")))] | length' <<< "$api_servers")" 3
check "API audit retention 30 days" "$(jq '[.items[] | select(any(.spec.containers[0].command[]; . == "--audit-log-maxage=30"))] | length' <<< "$api_servers")" 3
check "API server profiling disabled" "$(jq '[.items[] | select(any(.spec.containers[0].command[]; . == "--profiling=false"))] | length' <<< "$api_servers")" 3
check "Bound SA token extension disabled" "$(jq '[.items[] | select(any(.spec.containers[0].command[]; . == "--service-account-extend-token-expiration=false"))] | length' <<< "$api_servers")" 3

for ds in kube-bench-control-plane kube-bench-worker; do
  desired=$(kubectl -n security-system get ds "$ds" -o jsonpath='{.status.desiredNumberScheduled}')
  ready=$(kubectl -n security-system get ds "$ds" -o jsonpath='{.status.numberReady}')
  check "$ds coverage" "$ready" "$desired"
done

kube_bench_worker_fail=0
for pod in $(kubectl -n security-system get pods -l app.kubernetes.io/component=worker-benchmark -o name); do
  failed=$(kubectl -n security-system logs "$pod" | grep '^{' | tail -1 | jq -r '.Totals.total_fail')
  kube_bench_worker_fail=$((kube_bench_worker_fail + failed))
done
check "kube-bench worker CIS failures" "$kube_bench_worker_fail" 0

kube_bench_cp_fail=0
for pod in $(kubectl -n security-system get pods -l app.kubernetes.io/component=control-plane-benchmark -o name); do
  failed=$(kubectl -n security-system logs "$pod" | grep '^{' | tail -1 | jq -r '.Totals.total_fail')
  kube_bench_cp_fail=$((kube_bench_cp_fail + failed))
done
# Two accepted findings per control-plane: kubeadm etcd root ownership and the
# node-local kubelet serving CA, documented in the deployment report.
check "kube-bench accepted CP findings" "$kube_bench_cp_fail" 6

stale_rs_pods=$(kubectl get pods -A -o json | jq '[.items[] | select((.status.phase == "Failed" or .status.phase == "Succeeded") and .metadata.ownerReferences[0].kind == "ReplicaSet")] | length')
check "No stale failed ReplicaSet pods" "$stale_rs_pods" 0

sentinel_lock_active=false
if kubectl get validatingadmissionpolicybinding sentinel-experiment-resource-lock >/dev/null 2>&1; then
  sentinel_lock_active=true
fi
sentinel_controllers=$(kubectl -n production get deployment -o json | jq '[.items[] | select(.metadata.name == "loadgen" or .metadata.name == "nginx" or .metadata.name == "redis" or .metadata.name == "redis-loadgen")] | length')
if [[ "${sentinel_lock_active}" == "true" ]]; then
  printf 'INFO  %-42s %s\n' "Sentinel validation controllers (locked)" "${sentinel_controllers}"
fi
legacy_controllers=$(kubectl -n production get deployment,statefulset -o json | jq --argjson sentinel_lock "${sentinel_lock_active}" '[.items[] | select(.metadata.name == "aims-backend" or .metadata.name == "aims-traffic" or .metadata.name == "aims-postgres" or .metadata.name == "shop-frontend" or .metadata.name == "shop-loadgen" or ((.metadata.name == "loadgen" or .metadata.name == "nginx" or .metadata.name == "redis" or .metadata.name == "redis-loadgen") and ($sentinel_lock | not)))] | length')
check "No legacy/test production controllers" "$legacy_controllers" 0
check "CKS lab guardrails installed" "$(kubectl -n cks-lab get networkpolicy default-deny-all -o jsonpath='{.metadata.name}')" default-deny-all
check "Failed Kyverno policy reports" "$(kubectl get policyreports.wgpolicyk8s.io -A -o json | jq '[.items[] | select((.summary.fail // 0) > 0)] | length')" 0

latest_backup_phase=$(kubectl -n velero get backups.velero.io -o json | jq -r '[.items[] | select(.metadata.name | startswith("production-"))] | sort_by(.metadata.creationTimestamp) | last | .status.phase // "Missing"')
check "Latest production Velero backup" "$latest_backup_phase" Completed
latest_drill_phase=$(kubectl -n velero get restores.velero.io -l restore.aims.io/type=configmap-drill -o json | jq -r '.items | sort_by(.metadata.creationTimestamp) | last | .status.phase // "Missing"')
check "Latest isolated restore drill" "$latest_drill_phase" Completed
check "Restore drill namespace cleaned" "$(kubectl get namespace production-drill >/dev/null 2>&1 && printf present || printf absent)" absent

exit "$failures"
