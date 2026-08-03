# AIMS Backend

Django REST API for AIMS.

## Setup

From `Programming\backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env.local
```

Edit `.env.local` before running Django commands. `DATABASE_URL` must be a real
Supabase PostgreSQL URL. The placeholder in `.env.example` is only a template.
For local Windows development, prefer Supabase's Session pooler connection
string.

## Supabase Database

Recommended Session pooler format:

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

Direct connection format, only if your network supports IPv6 direct database
connections or your Supabase project has the IPv4 add-on enabled:

```env
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
```

Replace every placeholder with the values from Supabase. If `python manage.py
migrate` says it cannot resolve `db.<project-ref>.supabase.co`, switch
`DATABASE_URL` to the Session pooler URI from the Supabase dashboard's
**Connect** panel.

If your database password contains URL special characters such as `@`, `#`,
`%`, or `/`, URL-encode them before putting the password in `DATABASE_URL`.

## Run

```powershell
python manage.py check
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

API base URL:

```text
http://localhost:8000/api/
```

Health check:

```text
GET /api/health/
```

## Seed Demo Data

`python manage.py seed_demo` creates roles, demo manager/admin users, and 60
realistic products with image URLs. It is safe to run multiple times because
products are matched by barcode.

If the command fails with a `SyntaxError` near `<<<<<<<`, `=======`, or
`>>>>>>>`, resolve the Git conflict markers in
`apps\products\management\commands\seed_demo.py` first.

## Tests

```powershell
python manage.py check
pytest
```
