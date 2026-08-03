#!/usr/bin/env bash
set -euo pipefail

failures=0
check() {
  local label=$1 actual=$2 expected=$3
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS  %-44s %s\n' "$label" "$actual"
  else
    printf 'FAIL  %-44s actual=%s expected=%s\n' "$label" "$actual" "$expected"
    failures=$((failures + 1))
  fi
}

check "production PSA Restricted Enforce" \
  "$(kubectl get ns production -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')" restricted
check "CKS lab PSA Baseline Enforce" \
  "$(kubectl get ns cks-lab -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')" baseline
check "CKS student can list pods" \
  "$(kubectl auth can-i list pods --as=system:serviceaccount:cks-lab:cks-student -n cks-lab)" yes
check "CKS student cannot read secrets" \
  "$(kubectl auth can-i get secrets --as=system:serviceaccount:cks-lab:cks-student -n cks-lab)" no
check "CKS default deny NetworkPolicy" \
  "$(kubectl -n cks-lab get networkpolicy default-deny-all -o jsonpath='{.metadata.name}')" default-deny-all
check "Production mTLS STRICT" \
  "$(kubectl -n production get peerauthentication production-strict -o jsonpath='{.spec.mtls.mode}')" STRICT
check "Cilium L3-L7 policy valid" \
  "$(kubectl -n production get ciliumnetworkpolicy aims-zero-trust -o jsonpath='{.status.conditions[?(@.type=="Valid")].status}')" True
check "gVisor RuntimeClass" \
  "$(kubectl get runtimeclass sandbox -o jsonpath='{.handler}')" runsc
check "Kyverno runtime Enforce" \
  "$(kubectl get clusterpolicy production-runtime-hardening -o jsonpath='{.spec.validationFailureAction}')" Enforce
check "Gatekeeper runtime deny" \
  "$(kubectl get k8srequiredruntimehardening production-runtime-hardening -o jsonpath='{.spec.enforcementAction}')" deny
check "Ingress lab TLS certificate" \
  "$(kubectl -n istio-ingress get certificate aims-ingress-tls -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True

api_servers=$(kubectl -n kube-system get pods -l component=kube-apiserver -o json)
check "API audit enabled on 3 control planes" \
  "$(jq '[.items[] | select(any(.spec.containers[0].command[]; startswith("--audit-policy-file=")))] | length' <<< "$api_servers")" 3

check "kube-bench control-plane coverage" \
  "$(kubectl -n security-system get ds kube-bench-control-plane -o jsonpath='{.status.numberReady}')" \
  "$(kubectl -n security-system get ds kube-bench-control-plane -o jsonpath='{.status.desiredNumberScheduled}')"
check "kube-bench worker coverage" \
  "$(kubectl -n security-system get ds kube-bench-worker -o jsonpath='{.status.numberReady}')" \
  "$(kubectl -n security-system get ds kube-bench-worker -o jsonpath='{.status.desiredNumberScheduled}')"
check "Tetragon node coverage" \
  "$(kubectl -n kube-system get ds tetragon -o jsonpath='{.status.numberReady}')" \
  "$(kubectl -n kube-system get ds tetragon -o jsonpath='{.status.desiredNumberScheduled}')"
check "Falco node coverage" \
  "$(kubectl -n falco get ds falco -o jsonpath='{.status.numberReady}')" \
  "$(kubectl -n falco get ds falco -o jsonpath='{.status.desiredNumberScheduled}')"

report_count=$(kubectl get vulnerabilityreports.aquasecurity.github.io -A -o json | jq '.items | length')
reports_present=false
(( report_count > 0 )) && reports_present=true
check "Trivy vulnerability reports present" "$reports_present" true
check "Kyverno Cosign/SLSA policy ready" \
  "$(kubectl get clusterpolicy aims-verify-signed-slsa-images -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" True

psa_test=$(kubectl apply --dry-run=server -f - 2>&1 <<'YAML' || true
apiVersion: v1
kind: Pod
metadata:
  name: cks-psa-privileged-negative-test
  namespace: production
spec:
  containers:
    - name: test
      image: busybox:1.36
      securityContext:
        privileged: true
YAML
)
psa_denied=false
if grep -Eq 'violates PodSecurity.*restricted|privileged.*true' <<< "$psa_test"; then
  psa_denied=true
fi
check "PSA rejects privileged Pod" "$psa_denied" true

kyverno_test=$(kubectl apply --dry-run=server -f - 2>&1 <<'YAML' || true
apiVersion: v1
kind: Pod
metadata:
  name: cks-kyverno-readwrite-negative-test
  namespace: production
  labels:
    aims.hust.vn/runtime-hardened: "true"
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 1"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        readOnlyRootFilesystem: false
        runAsNonRoot: true
        runAsUser: 65534
YAML
)
kyverno_denied=false
if grep -Eq 'production-runtime-hardening|read-only root filesystem' <<< "$kyverno_test"; then
  kyverno_denied=true
fi
check "Kyverno rejects writable AIMS rootfs" "$kyverno_denied" true

gatekeeper_test=$(kubectl apply --dry-run=server -f - 2>&1 <<'YAML' || true
apiVersion: v1
kind: Pod
metadata:
  name: cks-gatekeeper-capabilities-negative-test
  namespace: cks-lab
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 1"]
      securityContext:
        allowPrivilegeEscalation: true
        runAsNonRoot: true
        runAsUser: 65534
YAML
)
gatekeeper_denied=false
if grep -Eq 'validation.gatekeeper.sh|must disable privilege escalation|must drop all Linux capabilities' <<< "$gatekeeper_test"; then
  gatekeeper_denied=true
fi
check "Gatekeeper rejects unsafe securityContext" "$gatekeeper_denied" true

if [[ "${1:-}" == "--show-negative-test" ]]; then
  printf '\nPSA response:\n%s\n' "$psa_test"
  printf '\nKyverno response:\n%s\n' "$kyverno_test"
  printf '\nGatekeeper response:\n%s\n' "$gatekeeper_test"
fi

exit "$failures"
