FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace definition and all packages first (for layer caching)
COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-events packages/shared-events/
COPY packages/shared-policies packages/shared-policies/
COPY packages/shared-personas packages/shared-personas/
COPY packages/shared-prompts packages/shared-prompts/
COPY services/robot-runtime services/robot-runtime/

RUN uv sync --package robot-runtime --no-dev

EXPOSE 8001
ENV PORT=8001

CMD ["uv", "run", "--package", "robot-runtime", "robot-runtime"]
