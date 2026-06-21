FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-config packages/shared-config/
COPY packages/shared-personas packages/shared-personas/
COPY services/identity-service services/identity-service/

RUN uv sync --package identity-service --no-dev

EXPOSE 8006
ENV PORT=8006

CMD ["uv", "run", "--package", "identity-service", "identity-service"]
