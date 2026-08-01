FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic sqlalchemy python-dotenv

EXPOSE 8000

CMD ["python", "-m", "app.main"]
