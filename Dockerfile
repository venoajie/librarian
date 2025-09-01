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
    mkdir -p /data/chroma && \
    mkdir -p /opt/healthcheck

# 3. Copy the virtual environment from the builder stage.
COPY --from=builder ${UV_VENV} ${UV_VENV}

# 4. Copy the application code.
COPY ./app /app/app

# 5. Copy the health check script.
COPY ./healthcheck/check.py /opt/healthcheck/check.py
RUN chmod +x /opt/healthcheck/check.py # Still run as root, so this will work.

# 6. Set ownership for ALL application-related files and directories at once.
#    This is the final privileged operation.
RUN chown -R appuser:appuser /app /data /opt/venv /opt/healthcheck

# --- END OF ROOT-LEVEL SETUP ---

# 7. Switch to the non-root user for all subsequent operations.
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

# The HEALTHCHECK command is metadata; it does not run during the build.
# It will be executed by the Docker daemon against the running container.
# We will use the new, more reliable Python script for the health check.
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
  CMD python /opt/healthcheck/check.py

# Set the entrypoint for the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]