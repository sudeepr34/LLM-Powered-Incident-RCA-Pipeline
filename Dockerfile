FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Copy the manifest first so dependency layers cache across code changes.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "pydantic>=2.6" \
    "sqlalchemy>=2.0" \
    "python-dotenv>=1.0" \
    "httpx>=0.27" \
    "psycopg[binary]>=3.1"

COPY app ./app
COPY sample_alerts.json ./

EXPOSE 8000

CMD ["python", "-m", "app.main", "--serve"]
