.PHONY: backend-check backend-test frontend-dev frontend-build frontend-lint

backend-check:
	cd backend && python manage.py check

backend-test:
	cd backend && pytest

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint
