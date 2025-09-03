# Dockerfile

# Stage 1: Base with UV and a Virtual Environment
FROM python:3.12-slim AS base

ENV UV_VENV=/opt/venv
RUN python -m pip install --no-cache-dir uv \
    && python -m uv venv ${UV_VENV}
ENV PATH="${UV_VENV}/bin:$PATH"

# Stage 2: Builder - Install dependencies with build tools
FROM base AS builder
# Install build tools only where needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
# --- OPTIMIZATION 1: Install CPU-only PyTorch ---
# This is significantly smaller than the default torch package.
RUN uv pip install torch --extra-index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --no-cache --strict .

# --- OPTIMIZATION 2: Dedicated, minimal model downloader stage ---
# This stage starts from the clean 'base', not the heavy 'builder'
FROM base AS model_downloader
ARG EMBEDDING_MODEL_NAME
ARG HF_HOME=/opt/huggingface_cache
ENV HUGGINGFACE_HUB_CACHE=${HF_HOME}
# Install only the single library needed to download the model
RUN uv pip install sentence-transformers
# Download the model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}', cache_folder='${HF_HOME}')"

# Stage 3: Runtime - Final, lean image
FROM base AS runtime

# --- ALL ROOT-LEVEL SETUP HAPPENS FIRST ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser

RUN mkdir -p /app && \
    mkdir -p /data/chroma

# Copy the lean virtual environment from the builder stage
COPY --from=builder ${UV_VENV} ${UV_VENV}

# Copy the pre-downloaded model cache from our new minimal downloader
ARG HF_HOME=/opt/huggingface_cache
ENV HUGGINGFACE_HUB_CACHE=${HF_HOME}
COPY --from=model_downloader ${HF_HOME} ${HF_HOME}

# Copy the application code
COPY ./app /app/app

# Set ownership for ALL application-related files and directories at once
RUN chown -R appuser:appuser /app /data /opt/venv ${HF_HOME}

# --- END OF ROOT-LEVEL SETUP ---
USER appuser
WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/.pycache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD ["curl", "-f", "http://localhost:8000/api/v1/health"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]