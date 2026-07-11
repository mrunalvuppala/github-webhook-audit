web: sh -c "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
worker: python -m celery -A app.tasks.celery_app worker --loglevel=info -Q agentaudit
