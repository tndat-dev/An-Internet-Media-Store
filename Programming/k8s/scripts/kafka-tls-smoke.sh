#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=${NAMESPACE:-production}
POD=${POD:-aims-kafka-smoke}
BOOTSTRAP=${BOOTSTRAP:-aims-kafka-kafka-bootstrap:9093}
TOPIC=${TOPIC:-aims-business-events}

cleanup() {
  kubectl -n "${NAMESPACE}" delete pod "${POD}" \
    --ignore-not-found=true --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
kubectl -n "${NAMESPACE}" wait --for=delete "pod/${POD}" \
  --timeout=90s >/dev/null 2>&1 || true

kubectl apply -f - <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: kafka-smoke
    app.kubernetes.io/part-of: aims
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: kafka
      image: quay.io/strimzi/kafka:1.1.0-kafka-4.3.0
      command: ["sh", "-c", "sleep 600"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 50m
          memory: 128Mi
        limits:
          cpu: 500m
          memory: 512Mi
      volumeMounts:
        - name: user-certs
          mountPath: /user-certs
          readOnly: true
        - name: cluster-ca
          mountPath: /cluster-ca
          readOnly: true
  volumes:
    - name: user-certs
      secret:
        secretName: aims-services
        defaultMode: 0440
    - name: cluster-ca
      secret:
        secretName: aims-kafka-cluster-ca-cert
        items:
          - key: ca.crt
            path: ca.crt
        defaultMode: 0440
YAML

kubectl -n "${NAMESPACE}" wait "pod/${POD}" \
  --for=condition=Ready --timeout=180s

kubectl -n "${NAMESPACE}" exec "${POD}" -- sh -c '
  password=$(cat /user-certs/user.password)
  printf "%s\n" \
    "security.protocol=SSL" \
    "ssl.truststore.type=PEM" \
    "ssl.truststore.location=/cluster-ca/ca.crt" \
    "ssl.keystore.type=PKCS12" \
    "ssl.keystore.location=/user-certs/user.p12" \
    "ssl.keystore.password=${password}" > /tmp/client.properties
'

topics=$(kubectl -n "${NAMESPACE}" exec "${POD}" -- \
  bin/kafka-topics.sh --bootstrap-server "${BOOTSTRAP}" \
  --command-config /tmp/client.properties --list)
grep -Fqx "${TOPIC}" <<<"${topics}"

message="aims-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "${message}" | kubectl -n "${NAMESPACE}" exec -i "${POD}" -- \
  bin/kafka-console-producer.sh --bootstrap-server "${BOOTSTRAP}" \
  --producer.config /tmp/client.properties --topic "${TOPIC}"

group="aims-smoke-$(date +%s)"
output=$(kubectl -n "${NAMESPACE}" exec "${POD}" -- \
  bin/kafka-console-consumer.sh --bootstrap-server "${BOOTSTRAP}" \
  --consumer.config /tmp/client.properties --topic "${TOPIC}" \
  --group "${group}" --from-beginning --timeout-ms 15000 2>/dev/null || true)

grep -Fqx "${message}" <<<"${output}"
printf 'PASS Kafka TLS produce/consume: %s\n' "${message}"
