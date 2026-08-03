# Local Development

## Backend

```bash
cd Programming/backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python manage.py check
pytest
```

## Frontend

```bash
cd Programming/frontend
npm install
npm run dev
```

For PayPal sandbox UI testing, create `Programming/frontend/.env.local` with:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_PAYPAL_CLIENT_ID=your_paypal_sandbox_client_id
```

## PostgreSQL

```bash
cd Programming
docker compose up -d postgres
```

Then set:

```text
DATABASE_URL=postgresql://aims:aims@localhost:5432/aims
```

## PayPal Sandbox Checklist

1. Put sandbox credentials in `Programming/backend/.env`.
2. Set `DATABASE_URL` to the Supabase Postgres connection string.
3. Put `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` and
	`NEXT_PUBLIC_PAYPAL_CLIENT_ID=...` in `Programming/frontend/.env.local`.
4. Start backend and frontend.
5. Open `/checkout/payment/card` and approve with a sandbox account.
