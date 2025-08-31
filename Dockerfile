# Dockerfile

# Stage 1: Base with UV and a Virtual Environment
FROM python:3.11-slim AS base
ENV UV_VENV=/opt/venv
# Install uv and create a virtual environment
RUN python -m pip install --no-cache-dir uv \
    && python -m uv venv ${UV_VENV}
# Add the venv to the PATH for subsequent stages
ENV PATH="${UV_VENV}/bin:$PATH"

# Stage 2: Builder - Install dependencies
FROM base AS builder
# Install build tools needed for compiling packages like psutil
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml .
# Install dependencies into the venv
RUN uv pip install --no-cache --strict .

# Stage 3: Runtime - Final, lean image
FROM base AS runtime

# Create the user's home directory
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser

# Copy the virtual environment
COPY --from=builder --chown=appuser:appuser ${UV_VENV} ${UV_VENV}

# Set the PATH to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# 1. Set the WORKDIR to be the project root
WORKDIR /app

# 2. Create and set permissions for the data directory
RUN mkdir -p /data/chroma && \
    chown -R appuser:appuser /data

# 3. Copy the 'app' package INTO the WORKDIR, creating the /app/app structure
COPY --chown=appuser:appuser ./app ./app

# 4. Switch to the non-root user
USER appuser

# Set environment variables. PYTHONPATH points to the project root.
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

# This command now works because PYTHONPATH is /app, and it can find the 'app.main' module.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]