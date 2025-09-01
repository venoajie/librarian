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
# 1. Set the WORKDIR to be the project root, /app.
WORKDIR /app

# 2. Create the data directory.
RUN mkdir -p /data/chroma

# 3. Copy the local 'app' directory INTO the WORKDIR, creating the required /app/app structure.
COPY --chown=appuser:appuser ./app ./app

# 4. Set ownership for all project and data directories.
RUN chown -R appuser:appuser /app /data

# 5. Switch to the non-root user.
USER appuser
# --- END FILE STRUCTURE SETUP ---

# Set PYTHONPATH to the project root so Python can find the 'app' package.
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

# This command now works because PYTHONPATH is /app, and it can find the 'app.main' module.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]