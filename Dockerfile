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

# Set the working directory
WORKDIR /app

# Create and set permissions for data directory
RUN mkdir -p /data/chroma && \
    chown -R appuser:appuser /data
USER appuser

# --- FIX: Copy the CONTENTS of the app directory, not the directory itself ---
# Note the trailing slash on './app/'
COPY --chown=appuser:appuser ./app/ .
# --- END FIX ---

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

# The command now correctly finds 'app.main' because 'main.py' is in the WORKDIR
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]