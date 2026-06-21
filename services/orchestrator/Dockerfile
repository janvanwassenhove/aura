FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-events packages/shared-events/
COPY packages/shared-policies packages/shared-policies/
COPY packages/shared-personas packages/shared-personas/
COPY packages/shared-prompts packages/shared-prompts/
COPY services/orchestrator services/orchestrator/

RUN uv sync --package orchestrator --no-dev

EXPOSE 8003
ENV PORT=8003

CMD ["uv", "run", "--package", "orchestrator", "orchestrator"]
