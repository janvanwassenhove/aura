FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-events packages/shared-events/
COPY services/memory-service services/memory-service/

RUN uv sync --package memory-service --no-dev

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8005
ENV PORT=8005

CMD ["uv", "run", "--package", "memory-service", "memory-service"]
