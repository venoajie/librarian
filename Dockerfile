# Dockerfile

# Stage 1: Base with UV and a Virtual Environment
FROM python:3.12-slim AS base

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

# --- FIX: Add the '-m' flag to create the user's home directory ---
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser
# --- END FIX ---

# Copy the virtual environment with installed dependencies from the builder stage
COPY --from=builder --chown=appuser:appuser ${UV_VENV} ${UV_VENV}

# This ensures the shell can find executables like 'uvicorn' inside the venv.
ENV PATH="/opt/venv/bin:$PATH"

# Set the working directory AFTER the user is created
WORKDIR /home/appuser/app

# Create and set permissions for data directory
RUN mkdir -p /data/chroma && \
    chown -R appuser:appuser /data
USER appuser

# Copy application code into the working directory
COPY --chown=appuser:appuser ./app .

# Set environment variables for better logging and to avoid writing .pyc files
ENV PYTHONPATH=/home/appuser/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]