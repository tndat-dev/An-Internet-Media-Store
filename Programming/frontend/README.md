# AIMS Frontend

Next.js frontend for AIMS.

## Setup

From `Programming\frontend`:

```powershell
npm install
npm run dev
```

The app runs at:

```text
http://localhost:3000
```

## Backend API

By default, the frontend calls:

```text
http://localhost:8000/api
```

You only need `.env.local` if your backend API runs somewhere else. If you
override the URL, include the `/api` suffix:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

The backend must be running separately:

```powershell
cd ..\backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

## Optional Supabase Frontend Keys

Only set these if a screen needs direct Supabase client access:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your_publishable_key
```

Product browsing, cart, checkout, manager, and admin screens normally talk to
the Django API instead of Supabase directly.

## Checks

```powershell
npm run typecheck
npm run build
```
