FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG DB_DRIVER="psycopg[binary]>=3.2.0,<4.0.0"

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . ${DB_DRIVER:+"$DB_DRIVER"}

RUN addgroup --system sparkpilot && \
    adduser --system --ingroup sparkpilot sparkpilot && \
    chown -R sparkpilot:sparkpilot /app

USER sparkpilot

EXPOSE 8000

CMD ["uvicorn", "sparkpilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
