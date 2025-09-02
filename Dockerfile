```dockerfile
# Dockerfile

# Stage 1: Base with UV and a Virtual Environment
FROM python:3.12-slim AS base

ENV UV_VENV=/opt/venv
RUN python -m pip install --no-cache-dir uv \
    && python -m uv venv ${UV_VENV}
ENV PATH="${UV_VENV}/bin:$PATH"

# Stage 2: Builder - Install dependencies
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml .
RUN uv pip install --no-cache --strict .

# Stage 3: Runtime - Final, lean image
FROM base AS runtime

# --- ALL ROOT-LEVEL SETUP HAPPENS FIRST ---

# 1. Create the non-root user and group.
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser

# 2. Create all necessary directories for the application.
RUN mkdir -p /app && \
    mkdir -p /data/chroma

# 3. Copy the virtual environment and curl from the builder stage.
COPY --from=builder ${UV_VENV} ${UV_VENV}
COPY --from=builder /usr/bin/curl /usr/bin/curl

# 4. Copy the application code.
COPY ./app /app/app

# 5. Set ownership for ALL application-related files and directories at once.
#    This is the final privileged operation.
RUN chown -R appuser:appuser /app /data /opt/venv

# --- END OF ROOT-LEVEL SETUP ---

# 6. Switch to the non-root user for all subsequent operations.
#    This is a security best practice.
USER appuser

# Set the working directory
WORKDIR /app

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

# The HEALTHCHECK command now uses the application's own health endpoint.
# The container will only be marked 'healthy' when the index is fully loaded
# and the endpoint returns a 200 OK status.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Set the entrypoint for the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
