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
