# Environment Variables

## Backend

```text
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=no-reply@aims.local
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
SUPABASE_URL=your_supabase_project_url
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
SUPABASE_SERVICE_ROLE_KEY=optional_server_only_service_role_key
PAYPAL_CLIENT_ID=your_paypal_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_paypal_sandbox_client_secret
PAYPAL_SANDBOX=true
PAYPAL_CURRENCY=USD
PAYPAL_VND_PER_USD=25000
```

`DATABASE_URL` must point to Supabase Postgres. The backend intentionally does
not fall back to SQLite, so local `db.sqlite3` files are not recreated.
The backend loads both `backend/.env` and `backend/.env.local`; values in
`.env.local` override `.env`.

The PayPal sandbox values must come from a sandbox app in the PayPal Developer
Dashboard. Order totals are stored in VND; PayPal checkout uses
`PAYPAL_CURRENCY` and `PAYPAL_VND_PER_USD` to derive the amount charged by
PayPal.

## Frontend

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_PAYPAL_CLIENT_ID=your_paypal_sandbox_client_id
NEXT_PUBLIC_PAYPAL_CURRENCY=USD
NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
```

`NEXT_PUBLIC_API_BASE_URL` should point to the backend host root. The payment
API client appends `/api/...` itself.
Next.js normally reads frontend env files only, but this project also loads
`NEXT_PUBLIC_SUPABASE_*` from `backend/.env.local` when those keys are not set
in the frontend environment.
