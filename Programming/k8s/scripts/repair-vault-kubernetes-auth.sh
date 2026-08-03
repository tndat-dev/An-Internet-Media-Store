#!/usr/bin/env bash
set -euo pipefail

# Rebind Vault Kubernetes auth after a kubeadm control-plane/CA rebuild.
# The root token is read in-memory and is never printed.
VAULT_NAMESPACE=${VAULT_NAMESPACE:-vault}
VAULT_POD=${VAULT_POD:-vault-0}
BOOTSTRAP_SECRET=${BOOTSTRAP_SECRET:-vault-bootstrap}
ESO_NAMESPACE=${ESO_NAMESPACE:-external-secrets}
ESO_SERVICE_ACCOUNT=${ESO_SERVICE_ACCOUNT:-external-secrets}
VAULT_ROLE=${VAULT_ROLE:-external-secrets}
KUBERNETES_HOST=${KUBERNETES_HOST:-https://10.96.0.1:443}

root_token=$(kubectl -n "${VAULT_NAMESPACE}" get secret "${BOOTSTRAP_SECRET}" \
  -o jsonpath='{.data.root-token}' | base64 -d)

kubectl -n "${VAULT_NAMESPACE}" exec "${VAULT_POD}" -- \
  env VAULT_TOKEN="${root_token}" vault write auth/kubernetes/config \
  kubernetes_host="${KUBERNETES_HOST}" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt="" \
  disable_iss_validation=true \
  disable_local_ca_jwt=false >/dev/null

jwt=$(kubectl -n "${ESO_NAMESPACE}" create token "${ESO_SERVICE_ACCOUNT}" \
  --duration=10m)
kubectl -n "${VAULT_NAMESPACE}" exec "${VAULT_POD}" -- sh -c \
  "VAULT_TOKEN= vault write -format=json auth/kubernetes/login \
  role='${VAULT_ROLE}' jwt='${jwt}'" | \
  jq -e '.auth.client_token != null' >/dev/null

kubectl annotate clustersecretstore vault \
  "force-sync=$(date +%s)" --overwrite >/dev/null
echo "Vault Kubernetes auth login verified; ClusterSecretStore refresh requested."

