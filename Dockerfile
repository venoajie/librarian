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

# Create the user with a home directory
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser

# Copy the populated virtual environment
COPY --from=builder --chown=appuser:appuser ${UV_VENV} ${UV_VENV}

# Set the PATH to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# --- THE DEFINITIVE FILE STRUCTURE SETUP ---
# 1. Set the working directory to /app
WORKDIR /app

# 2. Copy the CONTENTS of the local './app' directory into the container's /app directory.
#    The trailing slash on './app/' is critical. This creates a flat structure like /app/main.py.
COPY --chown=appuser:appuser ./app/ .

# 3. Create the data directory and set all ownership correctly
RUN mkdir -p /data/chroma && \
    chown -R appuser:appuser /app /data

# 4. Switch to the non-root user
USER appuser
# --- END FILE STRUCTURE SETUP ---

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

# This command now works because the WORKDIR is /app and main.py is directly inside it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]