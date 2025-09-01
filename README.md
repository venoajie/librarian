
# Librarian RAG Service (v1.0.0)

**Project ID:** `PROJ-LIBRARIAN-DECOUPLE`
**Status:** `Production Ready`

A standalone, containerized FastAPI service that acts as a centralized, secure, and maintainable source of contextual information for all development tools and agents.

## Phase Implementation Status
- **Phase 1: Service Scaffolding (`v0.1.0`)** - ✅ **Complete**
- **Phase 2: Core Logic Implementation (`v0.2.0`)** - ✅ **Complete**
- **Phase 3: Production Hardening (`v1.0.0`)** - ✅ **Complete**

## Production Hardening Features (v1.0.0)

- **API Rate Limiting:** Protects the `/context` endpoint from abuse. Configured via `RATE_LIMIT_ENABLED` and `RATE_LIMIT_TIMEFRAME` environment variables.
- **Enhanced Health Monitoring:** The `/health` endpoint now includes `cpu_load_percent` and `memory_usage_percent` for better observability and autoscaling triggers.
- **Docker Compose Integration:** A `docker-compose.yml` file is provided for streamlined local development and testing.
- **Operational Runbook:** This README now serves as a comprehensive guide for deployment, monitoring, and troubleshooting.

## Deployment & Operations


# Librarian RAG Service (v1.0.0)

**Project ID:** `PROJ-LIBRARIAN-DECOUPLE`
**Status:** `Production Ready`

A standalone, containerized FastAPI service that acts as a centralized, secure, and maintainable source of contextual information for all development tools and agents.

## Deployment & Operations

### 1. Prerequisites
- Docker & Docker Compose
- An OCI account with an Object Storage bucket.
- A running Redis instance.
- OCI credentials configured on the host machine.

### 2. Host Preparation (First-Time Setup)
Before the first deployment, prepare the host environment.

```bash
# 1. Create a system-level directory for OCI credentials to avoid SELinux issues.
sudo mkdir -p /opt/oci

# 2. Copy your OCI config and key file to the new location.
#    (Replace 'oci_api_key.pem' if your key file has a different name)
sudo cp ~/.oci/config ~/.oci/oci_api_key.pem /opt/oci/

# 3. IMPORTANT: Edit the config file to use a portable path for the key_file.
#    Change 'key_file=/home/opc/.oci/oci_api_key.pem' to 'key_file=~/.oci/oci_api_key.pem'
sudo nano /opt/oci/config

# 4. Set secure but readable permissions.
sudo chmod 644 /opt/oci/config
sudo chmod 644 /opt/oci/oci_api_key.pem

# 5. Create the host directory for the persistent ChromaDB volume.
sudo mkdir -p /data/librarian/chroma
sudo chown <your_user>:<your_group> /data/librarian/chroma # e.g., sudo chown opc:opc ...
```

### 3. Running with Docker Compose
```bash
# 1. Create the secrets file (only needed once).
mkdir -p secrets
echo -n "your-super-secret-key-here" > ./secrets/librarian_api_key.txt

# 2. Create and configure your .env file.
cp .env.example .env
nano .env # Set your OCI_BUCKET_NAME

# 3. Build and start the services.
docker compose up --build -d
```

## Index Management

The service consumes a pre-built index from OCI. Use the provided `create_index.py` script to generate this index.

```bash
# 1. Install script dependencies (run once)
pip install chromadb sentence-transformers langchain tqdm

# 2. Run the script, pointing it at the source code you want to index.
#    Ensure you are in the correct directory and using the correct path.
python create_index.py /path/to/your/project/src

# 3. Upload the resulting index.tar.gz to your OCI bucket.
#    (Use the 'oci os object put' command)
```

## **NEW:** Troubleshooting / Operational Runbook

This service is robust but operates in a complex environment. If you encounter issues, consult this guide.

### Symptom: `context: []` or Incorrect Context is Returned
This is the most common and subtle failure mode. It means the service is running, but the index is empty, corrupted, or mismatched.

**Cause:** A stale or incorrectly generated index is being loaded. This can be caused by a stale Docker cache, a stale bind mount, or an old index file in OCI.

**Solution: The "Clean Room" Reset Procedure.**
This sequence is the definitive way to reset the service to a known-good state. It wipes all local state and forces a fresh pull from your cloud source of truth.

```bash
# 1. Stop the service and PERMANENTLY DELETE all persistent data volumes.
docker compose down -v

# 2. Manually delete the host bind mount directory to ensure it's gone.
sudo rm -rf /data/librarian/chroma

# 3. Re-create the empty host directory with correct permissions.
mkdir -p /data/librarian/chroma
sudo chown <your_user>:<your_group> /data/librarian/chroma

# 4. Re-generate and re-upload a fresh index to OCI using create_index.py.
#    (This is a critical step to ensure the cloud artifact is not stale).

# 5. Force a full, no-cache rebuild and restart the service.
#    The --no-cache flag is CRITICAL to avoid using old, broken code layers.
docker compose build --no-cache
docker compose up -d
```

### Symptom: OCI `ConfigFileNotFound` Error on Startup
**Cause:** The container cannot access the OCI configuration files mounted from the host, typically due to strict SELinux policies on the user's home directory.
**Solution:** Do not mount from `~/.oci`. Use the recommended host preparation step to place credentials in `/opt/oci` and update `docker-compose.yml` to mount from there.

### Symptom: `PermissionError` on Startup
**Cause:** The non-root `appuser` inside the container does not have permission to write to its working directory or cache.
**Solution:** This is a `Dockerfile` bug. Ensure the `Dockerfile` includes steps to create the user's home directory (`useradd -m`) and `chown` the application's working directory.
```

### 4. Monitoring (Mini-Runbook)

- **Primary Health Check:**
  - **Endpoint:** `GET /api/v1/health`
  - **What to watch:**
    - `status`: Should be `"ok"`. If `"degraded"`, it means the `index_status` is not `"loaded"`. Check the service logs for errors during startup related to OCI or ChromaDB.
    - `resource_usage`: Monitor `cpu_load_percent` and `memory_usage_percent`. High sustained values may indicate a need to scale resources.

- **Logs:**
  - Check service logs for errors related to OCI connection, Redis connection, or ChromaDB queries. The service provides detailed error messages for these components.

### 5. Troubleshooting

- **`403 Forbidden` Errors:** The client is providing a missing or invalid `X-API-KEY` header.
- **`429 Too Many Requests` Errors:** The client has exceeded the configured rate limit.
- **`503 Service Unavailable` on `/context`:** This indicates the index is not loaded (`app.state.chroma_collection` is `None`). This is a startup issue. Check logs for failures during the OCI download or ChromaDB loading steps.
- **High Latency:**
  1. Check Redis connectivity. If logs show "Redis cache check failed", the service is falling back to ChromaDB for every query.
  2. Check `resource_usage` in the health endpoint. High CPU/memory may be throttling the application.
  3. The ChromaDB query itself may be slow. This may require re-indexing or optimizing the vector model (outside the scope of this service).

### 6. Load Testing
Before full production deployment, conduct load testing against the `/context` endpoint to determine the appropriate resource allocation (`cpu`, `memory`) and replica count for your expected workload. Tools like `k6`, `JMeter`, or `locust` can be used. Monitor the resource usage metrics from the `/health` endpoint during the test.

### 3. Accessing the API

The API documentation is available at `http://localhost:8000/api/docs`.

## API Contract

### Authentication
All requests to protected endpoints like `/api/v1/context` require an API key passed in the `X-API-KEY` header.

### Endpoints

#### Health Check
- **Endpoint:** `GET /api/v1/health`
- **Description:** Provides the current operational status of the service.
- **Success Response (`200 OK`):**
  ```json
  {
    "status": "degraded",
    "version": "0.1.0",
    "index_status": "loading",
    "index_last_modified": null
  }
  ```

#### Retrieve Context
- **Endpoint:** `POST /api/v1/context`
- **Description:** Retrieves relevant context chunks for a given query.
- **Example Request:**
  ```bash
  curl -X POST "http://localhost:8000/api/v1/context" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-super-secret-api-key" \
  -d '{
    "query": "How is authentication handled?",
    "max_results": 3
  }'
  ```
- **Success Response (`200 OK`):**
  ```json
  {
    "query_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "context": [
      {
        "content": "Placeholder content...",
        "metadata": {"source": "placeholder/file_0.py", "line": 0},
        "score": 0.95
      }
    ],
    "processing_time_ms": 25
  }
  ```

## Configuration

All configuration is managed via environment variables as defined in `.env.example`.

| Variable                | Description                                  | Required |
|-------------------------|----------------------------------------------|----------|
| `LIBRARIAN_API_KEY`     | Secret key for API authentication.           | **Yes**  |
| `OCI_BUCKET_NAME`       | OCI Object Storage bucket name.              | **Yes**  |
| `OCI_CONFIG_PATH`       | Path to OCI config file inside container.    | No       |
| `OCI_INDEX_OBJECT_NAME` | Name of the index file in the bucket.        | No       |
| `CHROMA_DB_PATH`        | Local path in container for ChromaDB.        | No       |
| `REDIS_URL`             | Connection URL for Redis cache.              | No       |
| `LOG_LEVEL`             | Logging level (e.g., INFO, DEBUG).           | No       |
| `SERVICE_VERSION`       | The version of the service.                  | No       |

# Librarian RAG Service
...
## Phase Implementation Status
- **Phase 1: Service Scaffolding (`v0.1.0`)** - ✅ **Complete**
- **Phase 2: Core Logic Implementation (`v0.2.0`)** - ✅ **Complete**
- **Phase 3: Production Hardening** - ⏳ **Pending**
...
## Configuration
...
| Variable                  | Description                                      | Required | Default Value               |
|---------------------------|--------------------------------------------------|----------|-----------------------------|
| `LIBRARIAN_API_KEY`       | Secret key for API authentication.               | **Yes**  | -                           |
| `OCI_BUCKET_NAME`         | OCI Object Storage bucket name.                  | **Yes**  | -                           |
| `OCI_CONFIG_PATH`         | Path to OCI config file inside container.        | No       | `/home/appuser/.oci/config` |
| `OCI_INDEX_OBJECT_NAME`   | Name of the index file in the bucket.            | No       | `index.tar.gz`              |
| `CHROMA_DB_PATH`          | Local path in container for ChromaDB.            | No       | `/data/chroma`              |
| `CHROMA_COLLECTION_NAME`  | The name of the collection within ChromaDB.      | No       | `codebase_collection`       |
| `REDIS_URL`               | Connection URL for Redis cache.                  | No       | `redis://localhost:6379/0`  |
| `REDIS_CACHE_TTL_SECONDS` | Time-to-live for cache entries in seconds.       | No       | `3600`                      |
| `LOG_LEVEL`               | Logging level (e.g., INFO, DEBUG).               | No       | `INFO`                      |
| `SERVICE_VERSION`         | The version of the service.                      | No       | `0.2.0`                     |