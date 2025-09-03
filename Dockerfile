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

# --- Model Downloader ---
FROM builder AS model_downloader

# Declare the build argument that will be passed in from docker-compose.yml
ARG EMBEDDING_MODEL_NAME
ARG HF_HOME=/opt/huggingface_cache
ENV HUGGINGFACE_HUB_CACHE=${HF_HOME}
# Use the build argument to download the correct model dynamically.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}', cache_folder='${HF_HOME}')"


# Stage 3: Runtime - Final, lean image
FROM base AS runtime

# --- ALL ROOT-LEVEL SETUP HAPPENS FIRST ---

# 1. Install curl and its dependencies.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# 2. Create the non-root user and group.
RUN groupadd -r appuser --gid=1001 && \
    useradd -r -m -g appuser --uid=1001 appuser

# 3. Create all necessary directories for the application.
RUN mkdir -p /app && \
    mkdir -p /data/chroma

# 4. Copy the virtual environment from the builder stage.
COPY --from=builder ${UV_VENV} ${UV_VENV}

# --- Copy the pre-downloaded model cache ---
ARG HF_HOME=/opt/huggingface_cache
ENV HUGGINGFACE_HUB_CACHE=${HF_HOME}
COPY --from=model_downloader ${HF_HOME} ${HF_HOME}

# 5. Copy the application code.
COPY ./app /app/app

# 6. Set ownership for ALL application-related files and directories at once.
RUN chown -R appuser:appuser /app /data /opt/venv ${HF_HOME}

# --- END OF ROOT-LEVEL SETUP ---

# 7. Switch to the non-root user for all subsequent operations.
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
