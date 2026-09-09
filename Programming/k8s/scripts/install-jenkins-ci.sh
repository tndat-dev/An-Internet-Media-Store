#!/usr/bin/env bash
set -euo pipefail

# Install or reconcile the AIMS Jenkins CI controller. Jenkins builds/tests and
# updates GitOps; it must never be granted deployment credentials for production.
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

for binary in kubectl helm; do
  command -v "${binary}" >/dev/null || {
    printf 'Missing required command: %s\n' "${binary}" >&2
    exit 1
  }
done

kubectl apply --server-side --force-conflicts \
  -f "${root}/platform/70-jenkins-namespace.yaml"
helm repo add jenkins https://charts.jenkins.io >/dev/null 2>&1 || true
helm repo update jenkins >/dev/null
helm upgrade --install aims-jenkins jenkins/jenkins \
  --namespace jenkins --version 5.9.56 \
  -f "${root}/platform/jenkins-values.yaml" \
  --wait --timeout 10m

kubectl -n jenkins rollout status statefulset/aims-jenkins --timeout=5m
printf '%s\n' 'Jenkins CI is Ready. Argo CD remains the sole production deployer.'
