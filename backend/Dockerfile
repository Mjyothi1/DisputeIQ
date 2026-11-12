FROM python:3.11-slim

# BOOTSTRAP_DEMO_DATA defaults to false: the container never fills a database on its own.
# Set it to true only for a brand-new, empty, isolated demo database (see RUN_LOCAL.md).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOOTSTRAP_DEMO_DATA=false

WORKDIR /app

# Production image: runtime + postgres extras only (no pytest/ruff/mypy).
COPY . .
RUN pip install --no-cache-dir -e ".[postgres]" \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
