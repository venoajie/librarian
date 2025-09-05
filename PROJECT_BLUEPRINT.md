# PROJECT BLUEPRINT: The Librarian Service

<!-- Version: 2.0 -->
<!-- Change Summary (v2.0): Major architectural migration from local ChromaDB to a centralized PostgreSQL backend with pgvector. The service is now a pure database client, consuming a lightweight manifest from OCI. This enables multi-project support and enhances scalability and reliability. -->

## 1. System Overview and Core Purpose

This document is the canonical source of truth for the architectural principles and governance of the Librarian service (`PROJ-LIBRARIAN-DECOUPLE`). It serves as a "constitution" for human developers and a "README for the AI," ensuring that all future development and operational procedures are aligned with the core design philosophy.

The Librarian is a standalone, containerized FastAPI service designed to act as a centralized, secure, and maintainable source of contextual information for all development tools and agents within the ecosystem. Its primary purpose is to **provide a scalable, production-grade API endpoint for RAG (Retrieval-Augmented Generation) queries against a central PostgreSQL database.**

### 1.1. Ecosystem Glossary

This glossary defines the core components and concepts of the Three-Tiered Development Ecosystem.

-   **Three-Tiered Ecosystem:** The overarching architecture composed of three decoupled components: The Product, The Conductor, and The Librarian.
-   **The Product:** The target application being developed (e.g., `my-ai-assistant`, `librarian-service`). It is the passive subject of analysis by an external CI/CD pipeline.
-   **The Conductor (AI Assistant):** The lightweight, user-facing CLI tool. It orchestrates development workflows and is a **thin client** that offloads all RAG operations to the Librarian.
-   **The Librarian (RAG Service):** The centralized, standalone, production-grade service responsible for executing RAG queries. It connects to a central PostgreSQL database and serves codebase-aware context via a secure API.
-   **Index Manifest (`index_manifest.json`):** The immutable integration contract created by the indexer. It is a small, self-describing JSON file stored in OCI Object Storage. It specifies the exact embedding model and **PostgreSQL table name** for a given project and branch, ensuring perfect compatibility and directing the Librarian to the correct data source.
-   **The Indexer (CI/CD Process):** A CI/CD workflow (e.g., GitHub Actions) that runs in a Product repository. It scans the codebase, generates vector embeddings, and populates the central PostgreSQL database. Its final act is to upload the `index_manifest.json` to OCI.

---

## 2. Core Architectural Principles

### 2.1. Decoupling as a First Principle
All RAG-related query logic—including model loading, embedding generation for queries, and vector search—is encapsulated within this service. Client applications **MUST NOT** contain any direct database clients or ML models; they **MUST** interact with the Librarian via its defined API contract.

### 2.2. Stateless and Scalable by Design
The service is designed to be stateless. All persistent state (the vector data) is externalized to a central PostgreSQL database. The service's configuration state (which table to query) is determined at startup by downloading a lightweight manifest from OCI. This architecture inherently supports horizontal scaling; multiple instances of the Librarian can be run behind a load balancer without shared state conflicts.

### 2.3. Configuration via Environment
The service strictly adheres to 12-Factor App principles by managing all configuration through environment variables. This includes the `DATABASE_URL` for connecting to PostgreSQL and OCI credentials for fetching the manifest. Sensitive information **MUST** be injected using a secure mechanism like Docker Secrets.

### 2.4. API-First Contract
The service is defined by its API. All interactions are governed by a clear, versioned, and machine-readable contract. The primary contract provides two endpoints:
-   **`/health`:** A comprehensive, unauthenticated endpoint for observability and monitoring.
-   **`/context`:** A secure, authenticated endpoint for the core function of retrieving context.

---

## 3. Service Architecture & Components

The Librarian is now a client to a larger data ecosystem.

```
+------------------------+      +----------------------+      +-----------------------------+
|   CI/CD Indexer for    |----->|  Central PostgreSQL  |<-----|     CI/CD Indexer for       |
| "my-ai-assistant" Repo |(1a)  | (with pgvector)      |(1b)  |   "librarian-service" Repo  |
+------------------------+      +----------+-----------+      +-----------------------------+
                                           | (3. Query)
                                           |
+------------------+      +----------------v---------------------+       +-----------------+
|  Client Agent    |----->|          Librarian Service (FastAPI)   |------>|      Redis      |
| (e.g. Conductor) | (2)  |                                        | (4)   | (Response Cache)|
+------------------+      | +-----------------+  +---------------+ |       +-----------------+
                          | | Sentence-       |  | OCI Client    | |
                          | | Transformer Model |  | (for Manifest)| |
                          | | (Query Encoder)   |  |               | |
                          | +-----------------+  +---------------+ |
                          +----------------------------------------+
                                      ^
                                      | (2a. Download Manifest)
                                      |
                               +------+---------------+
                               |  OCI Object Storage  |
                               | (Source of Truth for |
                               |  Manifests)          |
                               +----------------------+
```

-   **FastAPI Application (`app/`):** The core web service that exposes the API, handles authentication, and orchestrates all internal logic.
-   **Central PostgreSQL Database:** The external, canonical source of truth for all indexed vector data from all projects.
-   **OCI Object Storage:** A lightweight repository for storing `index_manifest.json` files. The Librarian downloads the relevant manifest at startup to discover which table to query in the database.
-   **Sentence Transformer Model:** The `BAAI/bge-large-en-v1.5` model is loaded into memory on startup. It is responsible for converting incoming text queries into vector embeddings. This model **MUST** match the model specified in the downloaded `index_manifest.json`.
-   **Redis:** A high-speed, in-memory caching layer for API responses.

---

## 4. The Data Lifecycle (Decoupled)

The service's effectiveness depends on a fresh and accurate index, which is managed by an external, automated data lifecycle.

**Stage 1: The Trigger (Git Push)**
*   A developer pushes a commit to a tracked branch in a Product repository (e.g., `my-ai-assistant`).

**Stage 2: Indexing (CI/CD Environment)**
*   A CI/CD pipeline executes the standalone `ai-index` script.
*   The script scans the repository, chunks the code, generates embeddings, and connects to the central PostgreSQL database.
*   It populates a project-and-branch-specific table (e.g., `codebase_collection_my_ai_assistant_develop`) with the vector data.

**Stage 3: Manifest Publication (Cloud Object Storage)**
*   After successfully populating the database, the CI/CD workflow generates an `index_manifest.json` file.
*   This small JSON file is uploaded to the central OCI Object Storage bucket, overwriting the `latest` version for that project and branch.

**Stage 4: Consumption (Librarian Service)**
*   On startup or restart, the Librarian service is configured via environment variables to look for a specific project and branch (e.g., `OCI_PROJECT_NAME="my-ai-assistant"`, `OCI_INDEX_BRANCH="develop"`).
*   It authenticates with OCI and downloads the corresponding `index_manifest.json`.
*   It parses the manifest to get the database table name.
*   It connects to the PostgreSQL database and prepares to query the specified table.

---
## 5. API & Data Contracts

### 5.1. `GET /api/v1/health`
-   **Response Model (`HealthResponse`):**
    -   `status`: "ok" or "degraded".
    -   `version`: The semantic version of the service.
    -   `db_status`: "connected" or "disconnected".
    -   `index_last_modified`: ISO 8601 timestamp of the last successful manifest load.
    -   `index_branch`: The git branch of the loaded index, from the manifest.
    -   `db_table_name`: The name of the PostgreSQL table the service is actively querying.

*(...other sections like Build System, Operational Governance, etc., would be updated to reflect the new dependencies and operational requirements like managing a database connection...)*
```

---

### **Updated `PROJECT_BLUEPRINT.md` for The AI Assistant (Conductor)**

This document should focus on the *production* side—how the indexer now populates a central database and supports multiple projects.

```markdown
# PROJECT BLUEPRINT: AI Assistant

<!-- Version: 4.0 -->
<!-- Change Summary (v4.0): The RAG pipeline's data layer has been migrated from local ChromaDB files to a centralized PostgreSQL database with pgvector. The indexer (`ai-index`) is now a database client that populates this central store, enabling a true multi-project RAG ecosystem. -->

## 6. Workflows

### 6.4. Codebase-Aware Analysis Workflow (RAG)
The standard flow is now a fully decoupled, multi-project capable, database-centric model:
1.  **Index (Automated per Project):** A developer pushes a commit to a Product repository (e.g., `my-ai-assistant` or `librarian-service`). The CI/CD pipeline in *that specific repository* runs the `ai-index` command. The command connects to the central PostgreSQL database, populates a unique table for that project and branch (e.g., `codebase_collection_librarian_service_develop`), and uploads a small `index_manifest.json` to a shared OCI bucket.
2.  **Serve (Centralized):** The standalone Librarian service is configured to serve a specific project's index. On startup, it downloads the relevant manifest from OCI to discover which table to query in the central database.
3.  **Query (Any Machine):** A developer runs an `ai "..."` command. The `RAGContextPlugin` in the Conductor makes a lightweight API call to the configured Librarian service, which returns the relevant context.

#### 6.5. The RAG Index Data Lifecycle
The lifecycle is now a robust, database-centric ETL process.

**Stage 1 & 2: Local Development & Git Push (The Trigger)**
*(Unchanged)*

**Stage 3: Indexing (CI/CD Environment)**
*   The `ai-index` command runs, connecting to the central PostgreSQL database via a `DATABASE_URL` secret.
*   It performs `DELETE` and `INSERT` operations to synchronize the data in a project-and-branch-specific table with the current state of the codebase.

**Stage 4: Manifest Publication (Cloud Object Storage)**
*   After the database is updated, the CI/CD workflow generates an `index_manifest.json`.
*   This manifest, containing the database table name, is uploaded to a project-and-branch-specific path in the central OCI bucket (e.g., `indexes/my-ai-assistant/develop/latest/index_manifest.json`).

**Stage 5: Consumption (Librarian Service)**
*   The Librarian service downloads the manifest from OCI to determine which table to query in the central PostgreSQL database.

---

## 8. Build System & Packaging Philosophy

### 8.2. Optional Dependencies for a Decoupled World
The packaging philosophy reflects the Three-Tiered architecture.
-   **Standard Installation (`pip install .`):** Installs the **thin client** Conductor. It is lightweight and does not include any heavy ML or database libraries.
-   **`[project.optional-dependencies].indexing`:** This group is for the **CI/CD environment only**. It installs the base Conductor package *plus* all the heavy libraries (`torch`, `sentence-transformers`, `sqlalchemy`, `psycopg2-binary`, `pgvector`, `oci`) required for the `ai-index` command to connect to the database and build the knowledge base.

---

## 10. Governance for the RAG Indexing Pipeline

The CI/CD-driven RAG pipeline is critical infrastructure. Its integrity is paramount.

### 10.4. The Index Manifest as the Integration Contract

To prevent configuration drift between the Producer (CI/CD) and the Consumer (Librarian), the system **MUST** treat the `index_manifest.json` file as the immutable, single source of truth for a given index artifact.

The Producer (`ai-index`) is responsible for writing the following critical metadata into the manifest:
*   `embedding_model`: The exact name of the sentence-transformer model used.
*   `db_table_name`: The exact name of the unique PostgreSQL table containing the data for this project and branch.
*   `branch`: The source control branch the index was built from.

The Consumer (Librarian) **MUST** read these values from the manifest upon startup and use them to configure its runtime behavior. It **MUST** prioritize the manifest's values over its own local environment variables for these specific settings to guarantee compatibility with the data source.

### 10.5. Data Isolation in the Central Database (NEW)

To support multiple projects concurrently, data isolation is mandatory.

-   **Table Naming Convention:** The `ai-index` script **MUST** generate a unique table name for each project and each branch. The canonical naming scheme is: `<base_collection_name>_<sanitized_project_name>_<sanitized_branch_name>`.
    -   Example for `my-ai-assistant`'s `develop` branch: `codebase_collection_my_ai_assistant_develop`.
    -   Example for `librarian-service`'s `feature/new-auth` branch: `codebase_collection_librarian_service_feature_new_auth`.
-   **Database Permissions:** It is highly recommended to use a single database user (`llm_app`) with `CREATE` and `USAGE` privileges on the public schema of a dedicated database (`llm_indexing`). This user can manage all project tables within that single database, simplifying connection management.
