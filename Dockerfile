# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps + uv in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --extra full --frozen --no-install-project

# Runtime
FROM python:3.12-slim

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime deps and create user
RUN apt-get update && apt-get install -y --no-install-recommends curl libexpat1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 stk

# Copy venv and app
COPY --from=builder --chown=stk:stk /app/.venv ./.venv
COPY --chown=stk:stk . .

# Create instance dir with correct ownership
RUN mkdir -p /app/instance && chown stk:stk /app/instance

USER stk

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "5000"]
