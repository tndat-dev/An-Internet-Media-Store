#!/usr/bin/env bash
# Lab-only destructive synthetic acceptance test. Creates sandbox orders.
set -euo pipefail

gateway=${AIMS_BASE_URL:-http://10.1.16.234:31088}
keycloak=${AIMS_KEYCLOAK_URL:-http://10.1.16.234:30080/auth}
run_id=${AIMS_TEST_RUN_ID:-$(date +%s)}
bootstrap_user="accept-bootstrap-${run_id}"
bootstrap_password="Aims-${run_id}-Pass!"
client_secret=$(kubectl -n production get secret aims-runtime -o jsonpath='{.data.KEYCLOAK_CLIENT_SECRET}' | base64 -d)

admin_token=$(curl -fsS -d grant_type=client_credentials -d client_id=aims-app \
  --data-urlencode "client_secret=${client_secret}" \
  "${keycloak}/realms/aims/protocol/openid-connect/token" | jq -r .access_token)
if [[ -z "${admin_token}" || "${admin_token}" == null ]]; then
  echo 'Keycloak client-credentials token unavailable' >&2
  exit 1
fi

cleanup() {
  local name user_id
  for name in "${bootstrap_user}" "accept-buyer-${run_id}" "accept-managed-${run_id}"; do
    user_id=$(curl -fsS -G -H "Authorization: Bearer ${admin_token}" \
      --data-urlencode "username=${name}" --data-urlencode 'exact=true' \
      "${keycloak}/admin/realms/aims/users" | jq -r --arg name "${name}" '.[] | select(.username == $name) | .id' | head -n1) || continue
    if [[ -n "${user_id}" ]]; then
      curl -fsS -X DELETE -H "Authorization: Bearer ${admin_token}" \
        "${keycloak}/admin/realms/aims/users/${user_id}" >/dev/null || true
    fi
  done
}
trap cleanup EXIT

registration=$(curl -fsS -H 'Host: aims.lab' -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg username "${bootstrap_user}" --arg email "${bootstrap_user}@example.test" \
       --arg password "${bootstrap_password}" \
       '{username:$username,email:$email,password:$password,fullName:"AIMS Acceptance Bootstrap"}')" \
  "${gateway}/api/auth/register/")
bootstrap_id=$(jq -r '.user.userId // empty' <<<"${registration}")
if [[ -z "${bootstrap_id}" ]]; then
  echo 'Bootstrap registration returned no user ID' >&2
  exit 1
fi

for role in ADMIN PRODUCT_MANAGER; do
  role_json=$(curl -fsS -H "Authorization: Bearer ${admin_token}" \
    "${keycloak}/admin/realms/aims/roles/${role}")
  curl -fsS -X POST -H "Authorization: Bearer ${admin_token}" \
    -H 'Content-Type: application/json' -d "[$role_json]" \
    "${keycloak}/admin/realms/aims/users/${bootstrap_id}/role-mappings/realm" >/dev/null
done

login=$(curl -fsS -H 'Host: aims.lab' -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg username "${bootstrap_user}" --arg password "${bootstrap_password}" \
       '{username:$username,password:$password}')" "${gateway}/api/auth/login/")
manager_token=$(jq -r '.token // empty' <<<"${login}")
roles=$(jq -r '.user.roles | join(",")' <<<"${login}")
if [[ -z "${manager_token}" || "${roles}" != *ADMIN* || "${roles}" != *PRODUCT_MANAGER* ]]; then
  echo "Bootstrap user lacks required manager/admin roles: ${roles}" >&2
  exit 1
fi

echo "Running synthetic acceptance test ${run_id} (bootstrap roles: ${roles})"
AIMS_BASE_URL="${gateway}" AIMS_TEST_RUN_ID="${run_id}" \
  AIMS_TEST_MANAGER_TOKEN="${manager_token}" AIMS_TEST_ADMIN_TOKEN="${manager_token}" \
  python3 Programming/k8s/scripts/test-aims-problem-statement.py
