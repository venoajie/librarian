# Librarian RAG Service (v1.0.0)

**Project ID:** `PROJ-LIBRARIAN-DECOUPLE`
**Status:** `Production Ready`

A standalone, containerized FastAPI service that acts as a centralized, secure, and maintainable source of contextual information for all development tools and agents.

## Phase Implementation Status
- **Phase 1: Service Scaffolding (`v0.1.0`)** - ✅ **Complete**
- **Phase 2: Core Logic Implementation (`v0.2.0`)** - ✅ **Complete**
- **Phase 3: Production Hardening (`v1.0.0`)** - ✅ **Complete**

## Production Hardening Features (v1.0.0)

- **Asynchronous Startup:** The service starts immediately while loading the index and embedding model in the background, allowing for faster deployments and better compatibility with container orchestrators.
- **Robust Health Checks:** The Docker `HEALTHCHECK` now queries the application's `/api/v1/health` endpoint, ensuring the container is only marked "healthy" when it's fully initialized and ready to serve requests.
- **API Rate Limiting:** Protects the `/context` endpoint from abuse. Configured via `RATE_LIMIT_ENABLED` and `RATE_LIMIT_TIMEFRAME` environment variables.
- **Enhanced Health Monitoring:** The `/health` endpoint now includes `cpu_load_percent` and `memory_usage_percent` for better observability and autoscaling triggers.
- **Docker Compose Integration:** A `docker-compose.yml` is provided for streamlined local development and testing, now using reliable named volumes.
- **Operational Runbook:** This README now serves as a comprehensive guide for deployment, monitoring, and troubleshooting.

## Performance & Deployment Notes

### CPU-Only Inference

The official Docker image for the Librarian service is deliberately built with a **CPU-only version of PyTorch**. This is an architectural decision to optimize for:

*   **Smaller Image Size:** Reduces storage costs and speeds up deployment.
*   **Lower Operational Cost:** The service can be run on standard, cost-effective CPU instances without the need for expensive GPU hardware.

The service is designed for efficient CPU-based inference for embedding and search operations. When provisioning resources, you do not need to consider GPU availability.

## Deployment & Operations


### Environment Variables

All configuration is managed via environment variables, typically loaded from a `.env` file.

-   `OCI_BUCKET_NAME`: **(Required)** The name of the OCI bucket where indexes are stored.
-   `OCI_INDEX_BRANCH`: **(Required)** The specific git branch for which this Librarian instance should fetch an index (e.g., `develop`, `main`). The service constructs the final object path dynamically using this value.
-   `LIBRARIAN_API_KEY_FILE`: **(Required for Docker Compose)** Path to the Docker secret file containing the API key. Set to `/run/secrets/librarian_api_key` by default.
-   `OCI_CONFIG_PATH`: **(Local Development Only)** Path inside the container to the OCI config file. Should be unset in production.
-   `REDIS_URL`: The connection URL for the Redis cache.
-   `EMBEDDING_MODEL_NAME`: The name of the embedding model to download and use. Must match the model used to build the index.
-   `RERANKER_MODEL_NAME`: The name of the Cross-Encoder model to use for reranking.
-   `RERANKING_ENABLED`: Set to `true` to enable the two-stage reranking pipeline.

### Deployment Models

This service supports two primary deployment models.

#### A) Production Deployment (Recommended: OCI Instance Principals)

This is the most secure method and requires no key files.

1.  Ensure the OCI Compute Instance has an IAM policy allowing it to read objects from the target bucket.
2.  In your production environment configuration (e.g., `.env` file), **DO NOT set the `OCI_CONFIG_PATH` variable.** The service will automatically detect and use the instance principal.
3.  In your container orchestration definition, **REMOVE** the volume mount for OCI credentials.
4.  Deploy the container. Authentication is automatic and secure.

#### B) Local Development Setup (using OCI Key Files)

This method mounts your local OCI key file into the container for testing.

**1. Host Preparation (One-Time Setup):**
Prepare a system-level directory to avoid potential SELinux issues with home directories.

```bash
# Create a secure, system-level directory
sudo mkdir -p /opt/oci

# Copy your OCI config and key file
sudo cp ~/.oci/config ~/.oci/your_api_key.pem /opt/oci/

# IMPORTANT: Edit the config to use a portable path for the key file.
# Change 'key_file=/home/your_user/.oci/your_api_key.pem' to 'key_file=~/.oci/your_api_key.pem'
sudo nano /opt/oci/config

# Set secure permissions
sudo chmod 644 /opt/oci/config /opt/oci/your_api_key.pem
```

**2. Running with Docker Compose:**
The provided `docker-compose.yml` is pre-configured for this method.

```bash
# 1. Create the API key secret file (if it doesn't exist).
mkdir -p secrets
echo -n "your-super-secret-key-here" > ./secrets/librarian_api_key.txt

# 2. Create and configure your .env file.
cp .env.example .env
# Edit .env and set OCI_BUCKET_NAME, OCI_INDEX_BRANCH, and
# OCI_CONFIG_PATH=/home/appuser/.oci/config
nano .env

# 3. Build and start the services.
docker compose up --build -d
```

## Integration Contract for Index Producers

Any external system (e.g., a CI/CD pipeline) that generates and uploads an index for consumption by this Librarian service **MUST** adhere to the following contract. This ensures compatibility and prevents silent failures.

### 1. OCI Object Storage Path

The index producer **MUST** upload the compressed archive (`index.tar.gz`) to a path that matches the following structure, which the Librarian service dynamically constructs:

-   **Path Structure:** `indexes/{branch_name}/latest/index.tar.gz`
-   **Example:** For the `develop` branch, the object must be at `indexes/develop/latest/index.tar.gz`.

### 2. The `index_manifest.json` Contract

The producer **MUST** create an `index_manifest.json` file at the root of the archive. The Librarian service treats this file as the single source of truth for the artifact's configuration. The manifest **MUST** contain the following keys:

-   `embedding_model`: The exact Hugging Face name of the sentence-transformer model used to create the embeddings (e.g., `BAAI/bge-large-en-v1.5`).
-   `chroma_collection_name`: The exact name of the collection created within the ChromaDB instance.
-   `branch`: The source control branch the index was built from.

The Librarian service will **fail to start** if its own configured `EMBEDDING_MODEL_NAME` does not match the `embedding_model` value in the manifest, providing a critical safety check against model mismatch.

## Index Management

The service consumes a pre-built index from OCI. Use the provided `create_index.py` script to generate this index.

```bash
# 1. Install script dependencies (run once)
pip install chromadb sentence-transformers langchain tqdm

# 2. Run the script, pointing it at the source code you want to index.
python create_index.py /path/to/your/project/src

# 3. Upload the resulting index.tar.gz to your OCI bucket.
#    (Use the 'oci os object put' command)
```

## Troubleshooting / Operational Runbook

This service is robust but operates in a complex environment. If you encounter issues, consult this guide.

### Symptom: `context: []` or Incorrect Context is Returned
This is the most common and subtle failure mode. It means the service is running, but the index is empty, corrupted, or mismatched.

**Cause:** An old index file in OCI or a stale Docker named volume.

**Solution: The "Forced Refresh" Procedure.**
This sequence is the definitive way to reset the service to a known-good state. It wipes all local state and forces a fresh pull from your cloud source of truth.

```bash
# 1. Stop the service and PERMANENTLY DELETE all persistent data volumes.
#    The -v flag is critical as it removes the named volumes (e.g., librarian_chroma_data).
docker compose down -v

# 2. (CRITICAL) Re-generate and re-upload a fresh index to OCI using create_index.py.
#    This ensures the cloud artifact itself is not stale.

# 3. Force a full, no-cache rebuild and restart the service.
#    The --no-cache flag is CRITICAL to avoid using old, broken code layers.
docker compose build --no-cache
docker compose up -d
```

### Symptom: OCI `ConfigFileNotFound` Error on Startup
**Cause:** The container cannot access the OCI configuration files mounted from the host, typically due to strict SELinux policies on the user's home directory.
**Solution:** Do not mount from `~/.oci`. Use the recommended host preparation step to place credentials in `/opt/oci` and ensure the `docker-compose.yml` mounts from there.

### Symptom: `PermissionError` on Startup
**Cause:** The non-root `appuser` inside the container does not have permission to write to its working directory or cache.
**Solution:** This is a `Dockerfile` bug. Ensure the `Dockerfile` includes steps to create the user's home directory (`useradd -m`) and `chown` the application's working directory. The provided `Dockerfile` handles this correctly.

### Monitoring
- **Primary Health Check:**
  - **Endpoint:** `GET /api/v1/health`
  - **What to watch:**
    - `status`: Should be `"ok"`. If `"degraded"`, it means the `index_status` is not `"loaded"`. Check the service logs for errors during startup related to OCI or ChromaDB.
    - `resource_usage`: Monitor `cpu_load_percent` and `memory_usage_percent`. High sustained values may indicate a need to scale resources.

- **Logs:**
  - Check service logs for errors related to OCI connection, Redis connection, or ChromaDB queries. The service provides detailed error messages for these components.

### Common API Errors
- **`403 Forbidden`:** The client is providing a missing or invalid `X-API-KEY` header.
- **`429 Too Many Requests`:** The client has exceeded the configured rate limit.
- **`503 Service Unavailable` on `/context`:** This indicates the index is not loaded (`app.state.chroma_collection` is `None`). This is an expected error if a request is made while the service is still in its `loading` state after a fresh start. The client should retry after a short delay.


## Integration Contract for Index Producers

Any external system (e.g., a CI/CD pipeline) that generates and uploads an index for consumption by this Librarian service **MUST** adhere to the following contract. This ensures compatibility and prevents silent failures.

### 1. OCI Object Storage Configuration

The index producer **MUST** be configured to upload to the same destination the Librarian is configured to read from. The required configuration is managed by the following environment variables:

| Variable                | Required Value                               | Purpose                                      |
| ----------------------- | -------------------------------------------- | -------------------------------------------- |
| `OCI_BUCKET_NAME`       | `bucket-rag-index-fra`                       | The canonical bucket for all service indexes. |
| `OCI_INDEX_OBJECT_NAME` | `indexes/<branch_name>/latest/index.tar.gz` | The required object path structure.          |

### 2. Embedding Model Configuration

The index producer **MUST** use the exact same embedding model as the Librarian service to ensure vector compatibility.

-   **Required Model:** `BAAI/bge-large-en-v1.5`

Failure to align on these configurations will result in a `404 Not Found` error during startup or, in the case of a model mismatch, a silent failure where the service returns irrelevant context.
