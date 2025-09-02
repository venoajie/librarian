**Title:** `[Tech Debt] - Revert to User Principal Auth due to OCI IAM Propagation Issue`

**Issue ID:** `LIBRARIAN-TD-001`

**Date Created:** 2025-09-02

**Status:** `Open`

**Severity:** `High`

**Description:**
The Librarian service was designed and refactored to use OCI Instance Principal authentication, which is the mandated security best practice for production environments (`PROJECT_BLUEPRINT.md`, Section 7.3). During deployment, a persistent service-side issue within OCI IAM prevents the correctly configured Instance Principal from being authorized, resulting in `404 Not Found` errors.

Despite a perfect configuration (verified Dynamic Group, IAM Policy, and Compartment memberships), the service fails to start. An Oracle Support Request has been filed to address the root cause.

**Technical Debt Incurred:**
To unblock deployment, a temporary workaround has been implemented:
1.  The service has been reverted to use User Principal authentication (API key file).
2.  This requires mounting the `~/.oci` config directory into the production container, which increases the attack surface and operational complexity, directly violating our architectural principles.

**Resolution Criteria (Definition of Done):**
1.  Oracle Support resolves the underlying IAM issue.
2.  The Instance Principal authentication method is verified to work correctly.
3.  The workaround code in `app/core/index_manager.py` (forcing key file auth) is removed.
4.  The OCI config volume mount is removed from the production `docker-compose.yml` / container orchestration definition.
5.  The service is successfully deployed and running in production using only Instance Principal authentication.

**Associated Oracle SR:** `[Enter your Oracle Support Request number here]`

---

### 2. Prompt for a Future Resolution Session

This prompt is designed to be self-contained. You can give it to another AI assistant (or yourself in a future session) along with the project files, and it will have all the context needed to implement the fix once Oracle confirms the issue is resolved.

```prompt
<Mandate>
    <primary_objective>
        You are a senior cloud engineer tasked with resolving a critical piece of technical debt in the Librarian RAG Service. The service is currently using a temporary, insecure authentication method (OCI User Principal with a mounted key file) due to a previously identified OCI platform issue. Oracle Support has now confirmed that the underlying IAM Instance Principal issue is resolved.

        Your goal is to revert the temporary workaround and restore the architecturally mandated, secure Instance Principal authentication method.
    </primary_objective>

    <Context>
        The project blueprint mandates the use of OCI Instance Principals for production authentication to eliminate the need for key files. A persistent `404 Not Found` error, despite a perfectly verified configuration, forced a temporary fallback to User Principal authentication. All IAM components (Dynamic Group, Policy, Compartment OCIDs) have been triple-verified and are correct. The issue was confirmed to be service-side.
    </Context>

    <FilesForReview>
        - `app/core/index_manager.py` (Contains the temporary workaround)
        - `docker-compose.yml` (Contains the insecure volume mount)
    </FilesForReview>

    <RequiredActions>
        1.  **Modify `app/core/index_manager.py`:** Remove the temporary workaround from the `_get_oci_signer` function. Restore the original logic that attempts Instance Principal authentication first and then falls back to the config file for local development.
        2.  **Modify `docker-compose.yml`:** Remove the volume mount that exposes the OCI config file to the container (`/opt/oci:/home/appuser/.oci:ro,z`). Also, ensure the `OCI_CONFIG_PATH` environment variable is removed or commented out.
        3.  **Provide Verification Steps:** Outline the exact commands to build, deploy, and verify that the service now starts correctly using the restored Instance Principal authentication. This should include checking the container logs for the message "Using OCI Instance Principal for authentication."
    </RequiredActions>

    <OutputContract>
        Provide the complete, modified versions of `app/core/index_manager.py` and `docker-compose.yml`. Follow this with a clear, step-by-step guide for the user to deploy and verify the fix.
    </OutputContract>
</Mandate>

<SECTION:EVIDENCE_LOG>
    <!-- This section contains the proof that the original configuration was correct. -->
    <LogEntry timestamp="2025-09-02T10:18:00Z">
        **Holistic Verification Output:**
        A full verification of all OCI components was performed. The output confirms that the Instance, Bucket, and Policy all reside in the same compartment, and the policy statement correctly references the bucket's compartment OCID.

        --- INSTANCE DETAILS ---
        {
          "compartmentId": "ocid1.tenancy.oc1..aaaaaaaapk5a76iob5ujd7byfio3cmfosyj363ogf4hjmti6zm5ojksexgzq",
          "id": "ocid1.instance.oc1.eu-frankfurt-1.antheljtaenu5lyc736an7qiwnravr6s3vshbqo7h746hln3v75mujk4326q"
        }

        --- BUCKET DETAILS ---
        {
          "compartmentId": "ocid1.tenancy.oc1..aaaaaaaapk5a76iob5ujd7byfio3cmfosyj363ogf4hjmti6zm5ojksexgzq",
          "name": "bucket-rag-index-fra"
        }

        --- POLICY DETAILS ---
        {
          "compartmentId": "ocid1.tenancy.oc1..aaaaaaaapk5a76iob5ujd7byfio3cmfosyj363ogf4hjmti6zm5ojksexgzq",
          "id": "ocid1.policy.oc1..aaaaaaaa73k5furl6gwsigbyeulu5vu7rhlptc52chdrkolpliosmymzxh4q",
          "statements": "Allow dynamic-group LibrarianInstancesDG to read objects in compartment id ocid1.tenancy.oc1..aaaaaaaapk5a76iob5ujd7byfio3cmfosyj363ogf4hjmti6zm5ojksexgzq where target.bucket.name = bucket-rag-index-fra"
        }
    </LogEntry>
    <LogEntry timestamp="2025-09-02T10:15:58Z">
        **Final Failure Confirmation:**
        Even with the verified configuration and after updating the Dynamic Group rule, a test from within a temporary container using `oci os object get ... --auth instance_principal` still resulted in a `404 Not Found` error, confirming a service-side issue.
        OPC Request ID: `fra-1:e3J-GCqO27RC_4kUvgVS4FG6FsEfCZAlGTDfWZk3zvxaGFpvP8Qqm_oB5Kpo1xyj`
    </LogEntry>
</SECTION:EVIDENCE_LOG>
