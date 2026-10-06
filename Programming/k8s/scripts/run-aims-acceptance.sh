#!/usr/bin/env bash
# Lab-only destructive synthetic acceptance test. Creates sandbox orders.
set -euo pipefail

gateway=${AIMS_BASE_URL:-http://10.1.16.234:31088}
run_id=${AIMS_TEST_RUN_ID:-$(date +%s)}
bootstrap_user="accept-bootstrap-${run_id}"
bootstrap_password="Aims-${run_id}-Pass!"
auth_pod=$(kubectl -n production get pod -l app.kubernetes.io/name=auth-service \
  -o jsonpath='{.items[0].metadata.name}')

cleanup() {
  kubectl -n production exec -i "${auth_pod}" -- env RUN_ID="${run_id}" python3 - <<'PY' || true
import os
import psycopg

run_id = os.environ["RUN_ID"]
usernames = [
    f"accept-bootstrap-{run_id}",
    f"accept-buyer-{run_id}",
    f"accept-managed-{run_id}",
]
with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
    connection.execute(
        "DELETE FROM auth_service.users WHERE username = ANY(%s)",
        (usernames,),
    )
PY
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

kubectl -n production exec -i "${auth_pod}" -- env USER_ID="${bootstrap_id}" python3 - <<'PY'
import os
import psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
    connection.execute(
        "UPDATE auth_service.users SET roles=%s, updated_at=now() WHERE user_id=%s",
        (["ADMIN", "CUSTOMER", "PRODUCT_MANAGER"], os.environ["USER_ID"]),
    )
PY

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
