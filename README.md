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

## Deployment & Operations

### 1. Prerequisites
- Docker & Docker Compose
- An OCI account with an Object Storage bucket.
- OCI credentials configured on the host machine.

### 2. Host Preparation (First-Time Setup for OCI Credentials)
Before the first deployment, prepare the host environment to securely provide OCI credentials to the container.

```bash
# 1. Create a system-level directory for OCI credentials to avoid SELinux issues.
sudo mkdir -p /opt/oci

# 2. Copy your OCI config and key file to the new location.
#    (Replace 'oci_api_key.pem' if your key file has a different name)
sudo cp ~/.oci/config ~/.oci/oci_api_key.pem /opt/oci/

# 3. IMPORTANT: Edit the config file to use a portable path for the key_file.
#    Change 'key_file=/home/your_user/.oci/oci_api_key.pem' to 'key_file=~/.oci/oci_api_key.pem'
sudo nano /opt/oci/config

# 4. Set secure but readable permissions.
sudo chmod 644 /opt/oci/config
sudo chmod 644 /opt/oci/oci_api_key.pem
```

### 3. Running with Docker Compose
The service now uses Docker-managed named volumes, which simplifies setup and improves reliability.

```bash
# 1. Create the secrets file (only needed once).
mkdir -p secrets
echo -n "your-super-secret-key-here" > ./secrets/librarian_api_key.txt

# 2. Create and configure your .env file.
cp .env.example .env
nano .env # Set your OCI_BUCKET_NAME

# 3. Build and start the services.
#    Docker will automatically create and manage the 'librarian_chroma_data' volume.
docker compose up --build -d
```

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
