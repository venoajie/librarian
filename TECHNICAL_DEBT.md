**Issue ID:** `LIBRARIAN-TD-001`

**Date Created:** 2025-09-02
**Date Resolved:** 2025-09-03

**Status:** `Closed - Resolved`

**Severity:** `High`

**Description:**
The Librarian service was designed to use OCI Instance Principal authentication. During deployment, persistent `404 Not Found` errors were encountered, leading to the incorrect suspicion that a service-side OCI IAM issue was preventing the Instance Principal from being authorized.

**Technical Debt Incurred:**
A temporary workaround using User Principal authentication was considered to unblock deployment.

**Resolution Summary:**
A comprehensive debugging session on 2025-09-03 proved the initial diagnosis was incorrect. The `404 Not Found` errors were **not caused by an authentication failure**. The root cause was a series of configuration mismatches between the CI/CD pipeline producing the index and the Librarian service consuming it (different bucket names, object paths, and embedding models).

Once these configurations were aligned and the OCI IAM policy syntax was corrected, the service successfully authenticated and started using the mandated **Instance Principal method**. The suspected OCI platform issue did not exist.

**Resolution Criteria (Definition of Done):**
-   [x] Oracle Support resolves the underlying IAM issue. *(N/A - Issue was a misdiagnosis of a configuration error.)*
-   [x] The Instance Principal authentication method is verified to work correctly. *(Verified 2025-09-03)*
-   [x] The workaround code in `app/core/index_manager.py` is confirmed to correctly prioritize Instance Principal.
-   [x] The OCI config volume mount is confirmed to be unnecessary for production in `docker-compose.yml`.
-   [x] The service is successfully deployed and running in production using only Instance Principal authentication. *(Verified 2025-09-03)*
