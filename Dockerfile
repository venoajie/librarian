
# Stage 1: Base with UV and a Virtual Environment
FROM python:3.13-slim AS base
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
# Install dependencies into the virtual environment using uv
RUN uv pip install --no-cache --system --strict .

# Stage 3: Runtime - Final, lean image
FROM base AS runtime

# Create a non-root user with a specific UID/GID for security
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -g appuser --uid=1001 appuser

# Copy the virtual environment with installed dependencies from the builder stage
COPY --from=builder --chown=appuser:appuser ${UV_VENV} ${UV_VENV}

# This ensures the shell can find executables like 'uvicorn' inside the venv.
ENV PATH="/opt/venv/bin:$PATH"

# Create and set permissions for data and app directories
WORKDIR /app
RUN mkdir -p /data/chroma && \
    chown -R appuser:appuser /app /data
USER appuser

# Copy application code
COPY --chown=appuser:appuser ./app ./app

# Set environment variables for better logging and to avoid writing .pyc files in the app dir
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]