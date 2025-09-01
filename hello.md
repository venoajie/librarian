
### **Phase 1: Solidify and Document (Immediate Actions)**

The first step is to capture this successful state and the knowledge gained.

**1.1. Commit the Final Working Code**
You have made several critical fixes to the `Dockerfile`, `docker-compose.yml`, `main.py`, `create_index.py`, and `schemas.py`. These changes are the "source of truth" for the working system. They must be committed to your Git repository.

```bash
# From inside your /data/apps/librarian directory
git add .
git commit -m "feat: Finalize v1.0 deployment configuration and logic

- Corrected Dockerfile for proper file structure and permissions.
- Updated ChromaDB to use cosine distance for vector search.
- Centralized the rate limiter and fixed all runtime bugs.
- The service is now stable and fully operational."
git push
```

**1.2. Tag the Production Release**
This commit represents the first stable, deployable version of your service. Tag it as `v1.0.0` so you can always return to this known-good state.

```bash
git tag v1.0.0
git push --tags
```

**1.3. Update the Operational Runbook (`README.md`)**
The debugging journey taught us valuable lessons. These must be documented for the next person (or your future self).

**Action:** Edit your `README.md` and add a "Troubleshooting" or "Operational Notes" section. Include these key findings:
*   **SELinux & Volumes:** "When deploying on Oracle Linux, mounting user home directories can fail silently due to SELinux. The recommended pattern is to use a system-level directory like `/opt/oci` for OCI credentials and ensure host file permissions are `644`."
*   **Docker Cache:** "If the service misbehaves after a code change, the Docker build cache may be stale. Force a full rebuild with `docker compose build --no-cache` to ensure the latest code is used."
*   **Persistent Data:** "The ChromaDB index is persistent. To start from a truly clean slate, you must run `docker compose down -v` and manually delete the bind mount source directory (e.g., `sudo rm -rf /data/librarian/chroma`)."

---

### **Phase 2: Integrate the Primary Client (The AI Assistant)**

The Librarian's purpose is to serve other tools. It's time to integrate your main client.

**2.1. Index the Target Codebase**
The current index is for the Librarian's own code. Now, create the *real* index for the project you want the AI Assistant to work on (e.g., your `trading-app`).

```bash
# From the /data/apps directory
# Delete the old test index artifacts
rm -f index.tar.gz
rm -rf index_build/

# Create the real index from your main project's source
python create_index.py /data/apps/trading-app/src

# Upload the new, real index to OCI
# (The oci os object put command from before)
```

**2.2. Refactor the AI Assistant**
Now, modify the AI Assistant's code to use the Librarian service.
1.  **Update Configuration:** Add `LIBRARIAN_API_URL` and `LIBRARIAN_API_KEY` to the AI Assistant's environment configuration.
2.  **Implement Client:** Use the `librarian_client.py` example we designed earlier to replace all of its local RAG logic with API calls to the Librarian.
3.  **Remove Dependencies:** In the AI Assistant's `pyproject.toml`, you can now **remove** the heavy dependencies like `torch`, `sentence-transformers`, `chromadb`, and `oci`. This is the primary benefit of the decoupling project.

---

### **Phase 3: Automate and Operationalize (Production Readiness)**

This phase turns your manually deployed service into a robust, automated piece of infrastructure.

**3.1. Automate the Indexing Pipeline**
This is the most important step for long-term value.
*   **Action:** Create a **GitHub Actions workflow** (e.g., `.github/workflows/smart-indexing.yml`) in your `trading-app` repository.
*   **Trigger:** This workflow should trigger on every `git push` to your main development branch.
*   **Steps:**
    1.  Check out the code.
    2.  Install Python and the dependencies needed for `create_index.py`.
    3.  Run `python create_index.py ./src`.
    4.  Configure OCI credentials (using GitHub Secrets).
    5.  Run `oci os object put ...` to upload the new `index.tar.gz`.

**3.2. Set Up Monitoring and Alerting**
*   **Action:** Configure a monitoring service (like Prometheus, Grafana, or your cloud provider's built-in tools) to poll the `http://<your-server-ip>:8000/api/v1/health` endpoint every minute.
*   **Alerting Rule:** Create an alert that notifies you (e.g., via Slack or email) if the health check fails or if the `status` field returns `"degraded"` for more than 5 consecutive minutes.

---

### **Phase 4: Future Development (The Roadmap)**

With the service stable, you can now plan for the future enhancements outlined in the `PROJECT_BLUEPRINT.md`.
*   **`v1.1` - Instance Principal Authentication:** Begin the work to remove the need for key files in production.
*   **`v1.2` - Automated Index Refresh:** Design and implement the secure webhook for hot-reloading the index.

