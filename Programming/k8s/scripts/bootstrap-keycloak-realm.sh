#!/usr/bin/env bash
set -euo pipefail

: "${KEYCLOAK_ADMIN_PASSWORD:?Set KEYCLOAK_ADMIN_PASSWORD in the environment}"
: "${AIMS_CLIENT_SECRET:?Set AIMS_CLIENT_SECRET in the environment}"

KEYCLOAK_NAMESPACE=${KEYCLOAK_NAMESPACE:-keycloak}
KEYCLOAK_POD=${KEYCLOAK_POD:-keycloak-keycloakx-0}
KEYCLOAK_ADMIN=${KEYCLOAK_ADMIN:-admin}
KEYCLOAK_SERVER=${KEYCLOAK_SERVER:-http://localhost:8080/auth}
KCADM=/opt/keycloak/bin/kcadm.sh
KCADM_CONFIG=/tmp/aims-kcadm.config

kcadm() {
  kubectl -n "${KEYCLOAK_NAMESPACE}" exec "${KEYCLOAK_POD}" -- \
    "${KCADM}" "$@" --config "${KCADM_CONFIG}"
}

kcadm config credentials --server "${KEYCLOAK_SERVER}" --realm master \
  --user "${KEYCLOAK_ADMIN}" --password "${KEYCLOAK_ADMIN_PASSWORD}" >/dev/null

if ! kcadm get realms/aims >/dev/null 2>&1; then
  kcadm create realms -s realm=aims -s enabled=true \
    -s displayName='AIMS Production' >/dev/null
fi

for role in app-user app-admin k8s-admin; do
  if ! kcadm get "roles/${role}" -r aims >/dev/null 2>&1; then
    kcadm create roles -r aims -s "name=${role}" >/dev/null
  fi
done

app_id=$(kcadm get clients -r aims -q clientId=aims-app --fields id --format csv \
  --noquotes | head -n1)
if [[ -z "${app_id}" ]]; then
  kcadm create clients -r aims \
    -s clientId=aims-app \
    -s enabled=true \
    -s publicClient=false \
    -s standardFlowEnabled=true \
    -s serviceAccountsEnabled=true \
    -s 'redirectUris=["http://10.1.16.234/*","http://10.1.16.238/*","http://10.1.16.239/*"]' \
    -s 'webOrigins=["http://10.1.16.234","http://10.1.16.238","http://10.1.16.239"]' \
    -s "secret=${AIMS_CLIENT_SECRET}" >/dev/null
else
  kcadm update "clients/${app_id}" -r aims \
    -s enabled=true -s publicClient=false -s standardFlowEnabled=true \
    -s serviceAccountsEnabled=true -s "secret=${AIMS_CLIENT_SECRET}" >/dev/null
fi

kube_id=$(kcadm get clients -r aims -q clientId=kubernetes --fields id --format csv \
  --noquotes | head -n1)
if [[ -z "${kube_id}" ]]; then
  kcadm create clients -r aims \
    -s clientId=kubernetes \
    -s enabled=true \
    -s publicClient=true \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s 'redirectUris=["http://localhost:*","http://127.0.0.1:*"]' \
    -s 'webOrigins=["+"]' >/dev/null
  kube_id=$(kcadm get clients -r aims -q clientId=kubernetes --fields id \
    --format csv --noquotes | head -n1)
fi

mapper_count=$(kcadm get "clients/${kube_id}/protocol-mappers/models" -r aims | \
  jq '[.[] | select(.name == "groups")] | length')
if [[ "${mapper_count}" -eq 0 ]]; then
  kcadm create "clients/${kube_id}/protocol-mappers/models" -r aims \
    -s name=groups \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-group-membership-mapper \
    -s 'config."full.path"=false' \
    -s 'config."claim.name"=groups' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' >/dev/null
fi

kubectl -n "${KEYCLOAK_NAMESPACE}" exec "${KEYCLOAK_POD}" -- \
  rm -f "${KCADM_CONFIG}"
echo "Keycloak realm aims and clients aims-app/kubernetes are configured."
