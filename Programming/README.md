# AIMS Programming

AIMS (An Internet Media Store) is a full-stack web app for an internet media store selling books, CDs,
DVDs, and newspapers.

- Frontend: Next.js, React, TypeScript
- Backend: Django, Django REST Framework
- Database: Supabase PostgreSQL through `DATABASE_URL`

## Important

The backend currently requires a real Supabase PostgreSQL connection string.
The placeholder value from `backend\.env.example` is not runnable. For local
Windows development, use Supabase's **Session pooler** connection string unless
you know your network supports direct IPv6 database connections.

```text
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

If you see this error:

```text
failed to resolve host 'db.<project-ref>.supabase.co'
```

then `.env` or `.env.local` is using Supabase's direct database host. Copy the
Session pooler URI from the Supabase dashboard's **Connect** panel and use that
as `DATABASE_URL` instead.

## Project Structure

```text
Programming/
  backend/    Django API and business logic
  frontend/   Next.js customer, checkout, manager, and admin UI
  database/   Database notes
  docs/       API and team documentation
```

## Backend Setup

Open a terminal at the repository root:

```powershell
cd Programming\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create backend environment values:

```powershell
Copy-Item .env.example .env.local
```

Edit `Programming\backend\.env.local` and set a real Supabase URL. A typical
Supabase session-pooler URL looks like this:

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

A direct Supabase URL is only valid if your network supports IPv6 direct
database connections or your Supabase project has the IPv4 add-on enabled:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
```

If your database password contains URL special characters such as `@`, `#`,
`%`, or `/`, URL-encode them before putting the password in `DATABASE_URL`.

Then run:

```powershell
python manage.py check
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The backend API will be available at:

```text
http://localhost:8000/api/
```

## Seed Data

`python manage.py seed_demo` is idempotent. It creates:

- roles: `ADMIN`, `PRODUCT_MANAGER`, `CUSTOMER`
- users: `admin`, `linh`, `lam`
- 60 realistic demo products with image URLs:
  - 15 books
  - 15 CDs
  - 15 DVDs
  - 15 newspapers

When `DATABASE_URL` points to Supabase, the seed command writes directly to
Supabase. Running it again skips existing products by barcode and backfills
missing product images for older seed rows.

If `seed_demo` fails with a `SyntaxError` pointing at `<<<<<<<`, `=======`, or
`>>>>>>>`, the file still contains unresolved Git conflict markers. Resolve
`Programming\backend\apps\products\management\commands\seed_demo.py` before
running the command.

## Frontend Setup

Open a second terminal:

```powershell
cd Programming\frontend
npm install
npm run dev
```

The frontend defaults to:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

You do not need a frontend `.env.local` for the default local backend. If you do
override `NEXT_PUBLIC_API_BASE_URL`, include the `/api` suffix.

The frontend will be available at:

```text
http://localhost:3000
```

## Demo Walkthrough

Customer flow:

```text
http://localhost:3000/
Browse products -> View details -> Add to cart -> Cart -> Delivery -> Invoice -> Payment
```

Manager product flow:

```text
http://localhost:3000/manager/products
Create, edit, deactivate, or delete products.
```

Admin user flow:

```text
http://localhost:3000/admin/users
Manage users and roles.
```

## Checks

Backend:

```powershell
cd Programming\backend
python manage.py check
pytest
```

Frontend:

```powershell
cd Programming\frontend
npm run typecheck
npm run build
```

## Kubernetes production-like lab

Desired state của cụm kubeadm và runbook CKS nằm trong [`k8s/`](k8s/). Bản đang
nghiệm thu gồm 9 Argo Rollout/18 backend pod, 2 frontend pod do Helm quản lý,
PSA Restricted Enforce, Istio Ambient mTLS STRICT, Gateway API HTTP/HTTPS,
Vault/ESO, operator dữ liệu, supply-chain policy và runtime detection.

```bash
cd Programming/k8s
scripts/verify-aims.sh
scripts/verify-cks-lab.sh
```

Các image `prod-sim` là artifact node-local dành cho lab. Pipeline GitLab đã có
luồng build → Trivy/kubesec → Syft SBOM → SLSA/Cosign attest → verify → cập nhật
digest Helm; cần registry/runner thật trước khi bật Cosign policy Enforce.
