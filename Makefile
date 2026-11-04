.PHONY: test api web

test:
	cd backend && .venv/bin/pytest -q

api:
	cd backend && .venv/bin/uvicorn app.main:app --port 8000

web:
	cd frontend && npm run dev
