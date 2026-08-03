# AIMS — An Internet Media Store

AIMS is a full-stack media-store application for browsing and purchasing books,
CDs, DVDs, and newspapers. It includes customer checkout, product management,
user administration, PayPal and VietQR payment flows, and deployment assets for
a production-like Kubernetes lab.

## Tech stack

- **Frontend:** Next.js, React, and TypeScript
- **Backend:** Django and Django REST Framework
- **Database:** Supabase PostgreSQL
- **Infrastructure:** Docker, Kubernetes, Helm, Argo Rollouts, Istio, and Vault

## Features

- Browse products and view product details
- Manage a shopping cart and delivery information
- Place orders and pay by credit card/PayPal or VietQR
- Create, update, deactivate, and delete products as a product manager
- Manage users and roles as an administrator
- Seed a repeatable demo catalog with 60 products
- Deploy and verify the application in a Kubernetes security lab

## Repository structure

```text
.
├── Programming/           Application source, setup guides, and deployment files
│   ├── backend/           Django REST API and business logic
│   ├── frontend/          Next.js web application
│   ├── database/          Database notes
│   ├── docs/              API, setup, and team documentation
│   └── k8s/               Helm chart, manifests, scripts, and CKS lab
├── RequirementAnalysis/   SRS, use cases, and activity diagrams
├── ArchitecturalDesign/   Class, sequence, and communication diagrams
├── DetailedDesign/        UI, data, class, and system-interface designs
├── GoodDesign/            Design principles and additional requirements
└── UnitTesting/           Test plans and test evidence
```

## Quick start

### Prerequisites

- Python 3 with `venv` and `pip`
- Node.js and npm
- A Supabase PostgreSQL project and connection string

### 1. Run the backend

```bash
cd Programming/backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env.local
```

On Windows PowerShell, activate the environment and copy the configuration with:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env.local
```

Set `DATABASE_URL` in `Programming/backend/.env.local` to a real Supabase
PostgreSQL connection string. The session pooler is recommended for local
networks without direct IPv6 connectivity:

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

Then initialize and start the API:

```bash
python manage.py check
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The API is available at `http://localhost:8000/api/`; its health endpoint is
`http://localhost:8000/api/health/`.

### 2. Run the frontend

In a second terminal:

```bash
cd Programming/frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend uses
`http://localhost:8000/api` by default. To point it elsewhere, copy
`Programming/frontend/.env.example` to `.env.local` and set
`NEXT_PUBLIC_API_BASE_URL`, including the `/api` suffix.

## Demo routes

| Area | URL | Purpose |
| --- | --- | --- |
| Store | `http://localhost:3000/` | Browse products and complete checkout |
| Product manager | `http://localhost:3000/manager/products` | Manage the catalog |
| Administration | `http://localhost:3000/admin/users` | Manage users and roles |

The idempotent `seed_demo` command creates the `ADMIN`, `PRODUCT_MANAGER`, and
`CUSTOMER` roles, demo users, and 60 products split evenly across the four media
types.

## Verification

Backend:

```bash
cd Programming/backend
python manage.py check
pytest
```

Frontend:

```bash
cd Programming/frontend
npm run typecheck
npm run lint
npm run build
```

## Kubernetes production deployment

The Kubernetes configuration under `Programming/k8s/` provides a hardened,
production-like deployment in the `production` namespace. Its target topology
uses three control-plane nodes and three workers, 9 Argo Rollouts (18 backend
pods), 2 frontend pods, highly available data services, strict mTLS, Restricted
Pod Security Admission, policy enforcement, observability, and Velero backups.

> The checked-in defaults are suitable for the on-premises lab. Before using
> them for a real production system, replace the node-local `prod-sim` images,
> self-signed `aims.lab` certificate, and demo OpenSearch certificates as
> described in [Production hardening](#production-hardening).

### Cluster prerequisites

Prepare a Kubernetes cluster with `kubectl`, `helm`, and `jq`, plus the
operators and CRDs required by the deployment:

- Argo Rollouts, CloudNativePG, Strimzi Kafka, RabbitMQ Cluster Operator
- Redis Operator, MinIO Operator, cert-manager, and Gateway API
- Istio Ambient Mesh, Kyverno, Gatekeeper, External Secrets, and Vault
- Velero, Trivy Operator, OpenTelemetry, Loki, Tempo, and OpenSearch

The deployment scripts stop immediately when a required core CRD is missing.
Store runtime credentials in Vault; never put database URLs, passwords, tokens,
or private keys in Git. `ExternalSecret` resources materialize those values as
the `aims-runtime` Kubernetes Secret.

### 1. Prepare worker nodes

Run the security-profile setup on every worker, then label nodes that support
the gVisor runtime:

```bash
cd Programming/k8s
sudo scripts/configure-gvisor-worker.sh
sudo scripts/install-node-security-profiles.sh \
  node-profiles/aims-runtime.json \
  node-profiles/aims-restricted.apparmor
kubectl label node <worker-name> runtime.gvisor.dev/enabled=true --overwrite
```

For the lab's node-local frontend image, label its two target workers:

```bash
scripts/label-lab-frontend-nodes.sh k8s-worker3.local k8s-worker4.local
```

Skip this lab-only label after publishing the frontend image to a registry and
removing `frontend.nodeSelector` from the Helm values.

### 2. Configure images, secrets, and ingress

Before reconciling the cluster:

1. Set the backend and frontend image repository/tag or immutable digest in
   `Programming/k8s/aims-chart/values.yaml`.
2. Populate the Vault `aims/production` path with every property referenced by
   `Programming/k8s/platform/15-external-secrets.yaml`.
3. Confirm that the `vault` `ClusterSecretStore` is `Ready`.
4. Configure production DNS, Gateway hostnames, and a trusted certificate
   issuer instead of the default `aims.lab` self-signed certificate.

```bash
kubectl get clustersecretstore vault
kubectl get gatewayclass
kubectl get nodes
```

### 3. Reconcile the platform

From `Programming/k8s`, deploy the complete platform after its operators are
installed:

```bash
scripts/deploy-aims-platform.sh
```

This applies namespace/RBAC, data and messaging services, external secrets,
security policies, observability, backup resources, the AIMS Helm release, and
Restricted PSA enforcement. To reconcile only AIMS resources without upgrading
the Loki, Tempo, and OpenSearch charts, use:

```bash
scripts/deploy-aims-resources.sh
```

For the full security upgrade workflow—including server-side dry runs,
kube-apiserver audit configuration, policy reconciliation, cleanup, and final
verification—run:

```bash
scripts/reconcile-security-upgrade.sh
```

### 4. Verify the deployment

```bash
scripts/verify-aims.sh
scripts/verify-cks-lab.sh
kubectl -n production get rollouts,pods,services,gateway
```

The verification scripts return a non-zero status if topology, workload
availability, data services, security controls, routing, runtime profiles,
backup, or legacy-controller cleanup does not match the expected state.

### Production hardening

Complete these items before exposing the system to production traffic:

- Publish backend and frontend images to a private registry and deploy immutable
  digests instead of node-local `prod-sim` tags.
- Run the GitLab supply-chain pipeline (Trivy/kubesec, Syft SBOM, SLSA
  provenance, and Cosign signing/attestation), verify it succeeds, then change
  the supply-chain policy from `Audit` to `Enforce`.
- Replace self-signed ingress and OpenSearch demo certificates with certificates
  issued by a trusted public or internal CA.
- Configure kube-apiserver OIDC with Keycloak for cluster-user authentication.
- Use dedicated persistent storage rather than sharing the worker OS/container
  disk, and validate capacity, replication, disruption budgets, and recovery
  objectives under load.
- Configure off-cluster Velero object storage and perform both metadata and full
  PostgreSQL/Kafka/volume restore drills.
- Connect real monitoring, alerting, log retention, on-call routing, and external
  dependency credentials for the target environment.

Create a backup and run the safe metadata restore drill with:

```bash
scripts/velero-smoke-backup.sh
kubectl -n velero get backups.velero.io
scripts/velero-config-restore-drill.sh
```

See the [Kubernetes runbook](Programming/k8s/README.md) and
[deployment report](AIMS_DEPLOYMENT_REPORT.md) for architecture, pinned chart
versions, operational caveats, audit logging, supply-chain policy, and recovery
details.

## Documentation

- [Application setup](Programming/README.md)
- [Backend guide](Programming/backend/README.md)
- [Frontend guide](Programming/frontend/README.md)
- [API endpoints](Programming/docs/api/api-endpoints.md)
- [Environment variables](Programming/docs/setup/environment-variables.md)
- [Kubernetes and Helm lab](Programming/k8s/README.md)
- [Software requirements specification](RequirementAnalysis/SRS/Group18SoftwareRequirementSpecification-Ver1.2.pdf)
- [Software design document](Group18-SDD.docx)

## Security notes

Do not commit `.env` or `.env.local` files. Keep database credentials, payment
provider secrets, and Supabase service-role keys out of client-side variables.
Only variables prefixed with `NEXT_PUBLIC_` should be exposed to the browser.
