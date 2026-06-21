FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages/shared-schemas packages/shared-schemas/
COPY packages/shared-events packages/shared-events/
COPY services/conversation-runtime services/conversation-runtime/

RUN uv sync --package conversation-runtime --no-dev

EXPOSE 8002
ENV PORT=8002

CMD ["uv", "run", "--package", "conversation-runtime", "conversation-runtime"]
