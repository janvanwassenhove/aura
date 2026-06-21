FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-config packages/shared-config/
COPY packages/shared-events packages/shared-events/
COPY services/connector-service services/connector-service/

RUN uv sync --package connector-service --no-dev

EXPOSE 8004
ENV PORT=8004

CMD ["uv", "run", "--package", "connector-service", "connector-service"]
