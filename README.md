
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

### 1. Prerequisites
- Docker & Docker Compose
- An OCI account with an Object Storage bucket containing the `index.tar.gz` file.
- A running Redis instance (can be deployed via the provided Docker Compose file).

### 2. Configuration
Copy `.env.example` to `.env` and populate it with your production values. Pay special attention to `LIBRARIAN_API_KEY`, `OCI_BUCKET_NAME`, and `REDIS_URL`.

### 3. Running with Docker Compose (Recommended)
This method starts the Librarian service and its Redis dependency together.

```bash
# Start the services in detached mode
docker-compose up --build -d

# To view logs
docker-compose logs -f librarian

# To stop the services
docker-compose down
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