# app\core\index_manager.py

import oci
import tarfile
import logging
from pathlib import Path
from .config import settings

logger = logging.getLogger(__name__)


def _get_oci_signer():
    """
    Determines the appropriate OCI authentication method.
    
    Tries Instance Principal first for production environments,
    then falls back to the config file for local development.
    """
    try:
        # This will succeed if running on an OCI compute instance with the correct policies.
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        logger.info("Using OCI Instance Principal for authentication.")
        # The config is only needed to get the tenancy OCID for the namespace call.
        # The signer handles the actual authentication.
        config = {"tenancy": signer.tenancy_id}
        return config, signer
    except (oci.exceptions.ConfigFileNotFound, oci.exceptions.MissingConfigValue, Exception):
        logger.info("Instance Principal not available. Falling back to OCI config file.")
        if not settings.OCI_CONFIG_PATH or not Path(settings.OCI_CONFIG_PATH).exists():
            logger.error(f"OCI_CONFIG_PATH '{settings.OCI_CONFIG_PATH}' is not configured or file does not exist.")
            raise oci.exceptions.ConfigFileNotFound("OCI config file not found for fallback authentication.")
        
        config = oci.config.from_file(settings.OCI_CONFIG_PATH)
        signer = oci.signer.Signer(
            tenancy=config["tenancy"],
            user=config["user"],
            fingerprint=config["fingerprint"],
            private_key_file_location=config.get("key_file"),
            pass_phrase=oci.config.get_config_value_or_default(config, "pass_phrase"),
        )
        return config, signer


def download_index_from_oci(destination_path: Path):
    """
    Downloads the index archive from OCI Object Storage using the best available auth method.
    """
    logger.info(f"Attempting to download '{settings.OCI_INDEX_OBJECT_NAME}' from bucket '{settings.OCI_BUCKET_NAME}'...")
    
    try:
        config, signer = _get_oci_signer()
        object_storage_client = oci.object_storage.ObjectStorageClient(config, signer=signer)
        
        # Namespace is often needed and can be retrieved using the authenticated client.
        namespace = object_storage_client.get_namespace().data

        get_obj = object_storage_client.get_object(
            namespace_name=namespace,
            bucket_name=settings.OCI_BUCKET_NAME,
            object_name=settings.OCI_INDEX_OBJECT_NAME
        )
        
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with open(destination_path, 'wb') as f:
            for chunk in get_obj.data.raw.stream(1024 * 1024, decode_content=False):
                f.write(chunk)
        
        logger.info("Successfully downloaded index from OCI.")
        return True
    except oci.exceptions.ServiceError as e:
        logger.error(f"OCI Service Error: Failed to download index. Status: {e.status}. Message: {e.message}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during OCI download: {e}", exc_info=True)
        return False

def unpack_index(archive_path: Path, destination_dir: Path):
    logger.info(f"Unpacking '{archive_path}' to '{destination_dir}'...")
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=destination_dir)
        logger.info("Index successfully unpacked.")
        return True
    except Exception as e:
        logger.error(f"Failed to unpack index archive: {e}", exc_info=True)
        return False