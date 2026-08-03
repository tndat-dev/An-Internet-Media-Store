# Database

Coding 1 treats Supabase as a managed PostgreSQL provider.

Django migrations are the source of truth for schema changes. SQL files in this
folder should be used later for Supabase exports, manual notes, or policies, not
as the primary schema definition.

For local development, run PostgreSQL through `Programming/docker-compose.yml` or
leave `DATABASE_URL` empty to use SQLite for the backend skeleton.
