FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Workspace root + lockfile
COPY pyproject.toml uv.lock ./

# All uv workspace members must be present for the workspace to resolve.
COPY packages/ packages/
COPY services/ services/
COPY apps/aura-brain apps/aura-brain/

RUN uv sync --package aura-brain --no-dev

EXPOSE 8000
ENV PORT=8000

CMD ["uv", "run", "--package", "aura-brain", "aura-brain"]
