# app\core\index_manager.py

import oci
import logging
import orjson
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .config import settings

logger = logging.getLogger(__name__)


def _get_oci_signer():
    """
    Determines the appropriate OCI authentication method, prioritizing Instance Principal.
    """
    try:
        logger.info("Attempting OCI Instance Principal authentication...")
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        config = {"region": signer.region}
        logger.info("Successfully authenticated using OCI Instance Principal.")
        return config, signer
    except Exception:
        logger.warning("Instance Principal authentication failed. Falling back to OCI config file.")
        
        if not settings.OCI_CONFIG_PATH or not Path(settings.OCI_CONFIG_PATH).exists():
            logger.error(f"OCI_CONFIG_PATH '{settings.OCI_CONFIG_PATH}' is not configured or file does not exist for fallback authentication.")
            raise oci.exceptions.ConfigFileNotFound("OCI config file not found for fallback authentication.")
        
        logger.info("Authenticating using OCI config file...")
        config = oci.config.from_file(settings.OCI_CONFIG_PATH)
        signer = oci.signer.Signer(
            tenancy=config["tenancy"],
            user=config["user"],
            fingerprint=config["fingerprint"],
            private_key_file_location=config.get("key_file"),
            pass_phrase=oci.config.get_config_value_or_default(config, "pass_phrase"),
        )
        logger.info("Successfully authenticated using OCI config file.")
        return config, signer

def _blocking_download_and_parse_manifest():
    """Synchronous helper to be run in a thread pool."""
    logger.info(f"Attempting to download '{settings.OCI_INDEX_OBJECT_NAME}' from bucket '{settings.OCI_BUCKET_NAME}'...")
    try:
        config, signer = _get_oci_signer()
        object_storage_client = oci.object_storage.ObjectStorageClient(config, signer=signer)
        
        namespace = object_storage_client.get_namespace().data

        get_obj = object_storage_client.get_object(
            namespace_name=namespace,
            bucket_name=settings.OCI_BUCKET_NAME,
            object_name=settings.OCI_INDEX_OBJECT_NAME
        )
        
        manifest_content = get_obj.data.raw.read()
        logger.info("Successfully downloaded manifest from OCI.")
        return orjson.loads(manifest_content)
    except oci.exceptions.ServiceError as e:
        logger.error(f"OCI Service Error: Failed to download manifest. Status: {e.status}. Message: {e.message}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during OCI download or parsing: {e}", exc_info=True)
        raise

async def download_manifest_from_oci(executor: ThreadPoolExecutor):
    """
    Downloads and parses the index manifest from OCI Object Storage asynchronously.
    """
    loop = asyncio.get_running_loop()
    manifest_data = await loop.run_in_executor(
        executor, _blocking_download_and_parse_manifest
    )
    return manifest_data
