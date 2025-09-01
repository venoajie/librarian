# PROJECT BLUEPRINT: The Librarian Service

<!-- Version: 1.0 -->
<!-- Change Summary (v1.0): Initial blueprint created upon successful first deployment. Documents the final decoupled, cloud-centric RAG architecture. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the Librarian service (`PROJ-LIBRARIAN-DECOUPLE`). It serves as a "constitution" for human developers and a "README for the AI," ensuring that all future development and operational procedures are aligned with the core design philosophy.

The Librarian is a standalone, containerized FastAPI service designed to act as a centralized, secure, and maintainable source of contextual information for all development tools and agents within the ecosystem. Its primary purpose is to **decouple the resource-intensive RAG (Retrieval-Augmented Generation) pipeline** from client applications, providing a single, authoritative source for codebase-aware context.

---

## 2. Core Architectural Principles

The architecture is built on four foundational principles:

### 2.1. Decoupling as a First Principle
The service's existence is predicated on the principle of decoupling. All RAG-related logic—including model loading, index management, and vector search—is encapsulated within this service. Client applications **MUST NOT** contain any direct RAG implementation details; they **MUST** interact with the Librarian via its defined API contract.

### 2.2. Stateless and Scalable by Design
The service is designed to be stateless from the perspective of a container orchestrator. All persistent state (the vector index) is externalized to a cloud object store and treated as an immutable, disposable asset that is loaded on startup. This architecture inherently supports horizontal scaling; multiple instances of the Librarian can be run behind a load balancer without shared state conflicts.

### 2.3. Configuration via Environment
The service strictly adheres to 12-Factor App principles by managing all configuration through environment variables. Sensitive information, such as the API key, **MUST** be injected using a secure mechanism like Docker Secrets, with the application reading the *path* to the secret from an environment variable. Hardcoding configuration values is strictly forbidden.

### 2.4. API-First Contract
The service is defined by its API. All interactions are governed by a clear, versioned, and machine-readable contract. The primary contract provides two endpoints:
-   **`/health`:** A comprehensive, unauthenticated endpoint for observability and monitoring.
-   **`/context`:** A secure, authenticated endpoint for the core function of retrieving context.

---

## 3. Service Architecture & Components

The Librarian is a composite service that orchestrates several best-in-class components to deliver its functionality.

```
                               +---------------------------------+
                               |        OCI Object Storage       |
                               | (Single Source of Truth for Index) |
                               +-----------------+---------------+
                                                 | (1. Download on Startup)
                                                 |
+------------------+       +---------------------+---------------------+       +-----------------+
|  Client Agent    |-----> |          Librarian Service (FastAPI)        | <---> |      Redis      |
| (with API Key)   |       |                                             |       | (Response Cache)|
+------------------+       | +-----------------+  +--------------------+ |       +-----------------+
                         | | Sentence-       |  |      ChromaDB      | |
                         | | Transformer Model |  | (Vector Search)    | |
                         | | (Query Encoder)   |  |                    | |
                         | +-----------------+  +--------------------+ |
                         +---------------------------------------------+
```

-   **FastAPI Application (`app/`):** The core web service that exposes the API, handles authentication, and orchestrates all internal logic.
-   **OCI Object Storage:** The canonical, centralized repository for the compressed vector index (`index.tar.gz`). This is the single source of truth.
-   **Sentence Transformer Model:** The `all-MiniLM-L6-v2` model is loaded into memory on startup. It is responsible for converting incoming text queries into vector embeddings that can be understood by the search index.
-   **ChromaDB:** The vector database engine. It is initialized on startup from the index downloaded from OCI and performs the high-speed cosine similarity search.
-   **Redis:** A high-speed, in-memory caching layer. It stores the results of identical queries to reduce latency and offload work from the embedding model and ChromaDB.

---

## 4. The Index Data Lifecycle


The service's effectiveness depends on a fresh and accurate index. This is managed by a robust, automated data lifecycle that is decoupled from the service itself.

**Stage 1: The Trigger (Git Push)**
*   The workflow is triggered when a developer executes a `git push` to a tracked branch on the remote repository.

**Stage 2: Indexing (CI/CD Environment)**
*   A CI/CD pipeline (e.g., GitHub Actions) checks out the specific commit.
*   It executes the standalone `create_index.py` script. This script scans the repository, chunks the code, and uses the `sentence-transformers` library to build a complete, `cosine`-based vector database.

**Stage 3: Centralization (Cloud Object Storage)**
*   The CI/CD workflow compresses the resulting database into an `index.tar.gz` archive. **Crucially, the archive MUST be structured with the database files at the root, not nested in subdirectories.**
*   This archive is uploaded to the central OCI Object Storage bucket, overwriting the `latest` version for that branch.

**Stage 4: Consumption (Librarian Service)**
*   On startup or restart, the Librarian service authenticates with OCI.
*   It downloads the latest `index.tar.gz` archive into its container.
*   It unpacks the archive and loads the database into its local ChromaDB instance.

---

## 5. API & Data Contracts

The service's behavior is strictly defined by its Pydantic schemas and API endpoints.

### 5.1. `GET /api/v1/health`
-   **Purpose:** Provides a detailed, real-time snapshot of the service's health.
-   **Authentication:** None.
-   **Response Model (`HealthResponse`):**
    -   `status`: "ok" or "degraded" (degraded if the index is not loaded).
    -   `version`: The semantic version of the service.
    -   `index_status`: "loaded", "loading", or "not_found".
    -   `index_last_modified`: ISO 8601 timestamp of the last successful index load.
    -   `resource_usage`: Real-time `cpu_load_percent` and `memory_usage_percent`.

### 5.2. `POST /api/v1/context`
-   **Purpose:** The core function. Retrieves relevant context chunks for a given query.
-   **Authentication:** Required. A valid API key **MUST** be provided in the `X-API-KEY` header.
-   **Request Model (`ContextRequest`):**
    -   `query`: The user's text query.
    -   `max_results`: The desired number of context chunks.
-   **Response Model (`ContextResponse`):**
    -   `query_id`: A unique UUID for the request.
    -   `context`: A list of `ContextChunk` objects, each containing `content`, `metadata`, and `score`.
    -   `processing_time_ms`: The total server-side processing time.

---

## 6. Build System & Packaging

The project adheres to modern Python packaging standards to ensure reliability and performance.

-   **Dependency Management:** All dependencies are managed in `pyproject.toml`.
-   **Build Process:** The service is built into a container image using a multi-stage `Dockerfile`.
    -   **Build Speed:** The `uv` package installer is used in the `builder` stage for significantly faster dependency resolution and installation than standard `pip`.
    -   **Security & Size:** The final `runtime` image is minimal. It includes the Python runtime and the pre-built virtual environment but excludes all build tools (like `gcc`), resulting in a smaller and more secure production artifact.

---

## 7. Operational Governance & Monitoring

The service is designed to be operated as a reliable piece of infrastructure.

-   **Primary Monitoring:** The `/health` endpoint is the primary tool for monitoring. An external uptime checker **MUST** be configured to poll this endpoint. Alerts **SHOULD** be triggered if the `status` is "degraded" for an extended period after a restart.
-   **Resource Scaling:** The `resource_usage` metrics in the health check should be ingested by a monitoring platform to inform scaling decisions. High sustained CPU or memory usage indicates a need to scale the underlying container resources.
-   **Security:**
    -   The API key **MUST** be treated as a production secret and rotated periodically.
    -   The OCI credentials **MUST** be managed securely. The recommended production pattern is to use OCI Instance Principal authentication, which eliminates the need for key files on the server.
-   **Logging:** The service produces structured logs. These logs **SHOULD** be forwarded to a centralized logging platform for analysis and alerting.

---

## 8. Governance for RAG Pipeline Integrity & Testing

The project formally recognizes that ensuring the health and effectiveness of the RAG pipeline is a distinct engineering discipline, separate from traditional software testing. A successful deployment of the Python codebase does not guarantee the success or relevance of the knowledge base it produces. This distinction can be understood through an analogy:
-   **Code Correctness (The Mechanic):** Traditional testing ensures the machinery works. Does the engine start? Do the wheels turn?
-   **Knowledge Relevance (The Librarian):** RAG pipeline testing ensures the quality of the library's content. Are the books relevant? Is the card catalog accurate?

To govern this second discipline, the project mandates the following RAG Pipeline Testing Protocol.

### 8.1. Health & Robustness (Is the library open and the catalog intact?)
This layer ensures the data pipeline is functional and complete.

-   **CI Sanity Check:** The CI/CD workflow **MUST** include a "Sanity Check" step after every indexing run. This step **MUST** fail the build if the total number of indexed files falls below a project-specific, reasonable threshold. This is a critical guardrail against silent failures caused by overly aggressive ignore patterns or incorrect source directory paths.
-   **Vector Metric Consistency:** The vector distance metric (e.g., `cosine`) **MUST** be explicitly defined and synchronized between the indexing script (`create_index.py`) and the service (`main.py`). A mismatch will result in a silent failure where no context is returned.

### 8.2. Effectiveness (Can the assistant find the right information?)
This layer measures the *quality* and *relevance* of the RAG system's output.

-   **The "Golden Set" Evaluation:** The project **MUST** maintain a curated "golden set" of questions and expected outcomes in a version-controlled file (e.g., `tests/rag_evaluation_set.yml`). This set represents the core knowledge the RAG system is expected to possess.
-   **Automated Evaluation:** An automated script (`scripts/evaluate_rag.py`) **MUST** be created to test the RAG pipeline against this golden set. This script will programmatically query the RAG system and measure key metrics, such as retrieval precision.
-   **CI Quality Gate:** The automated evaluation script **MUST** be run as a job in the CI pipeline after a new index is built. A drop in precision below a defined threshold **MUST** fail the build.


## 9. Future Roadmap

The `v1.0` service is complete and operational. The following enhancements are prioritized for future development:

-   **`v1.1` - Instance Principal Authentication:** Refactor the OCI client to use instance principals, removing the need to mount key files into the container in production.
-   **`v1.2` - Automated Index Refresh:** Implement a secure webhook (`/admin/refresh-index`) to allow the service to download and reload the index from OCI without a full container restart.
-   **`v1.3` - Formal Test Suite:** Develop a comprehensive `pytest` suite with unit and integration tests to improve maintainability and prevent regressions.
-   **`v2.0` - High Availability:** Document and test a deployment pattern for running multiple Librarian instances behind a load balancer, using a shared Redis Cluster for caching.