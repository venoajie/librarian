
import oci
import tarfile
import logging
import os
from pathlib import Path
from .config import settings

logger = logging.getLogger(__name__)

# --- MOCK FUNCTIONS FOR SIMULATION (Remove in real implementation) ---
def _mock_oci_download(destination_path: Path):
    """Simulates downloading the index from OCI."""
    logger.warning("--- USING MOCK OCI DOWNLOAD ---")
    # Create a dummy tar.gz file to simulate the download
    dummy_dir = Path("./dummy_index_src")
    dummy_dir.mkdir(exist_ok=True)
    (dummy_dir / "dummy_file.txt").write_text("This is a dummy index file.")
    
    with tarfile.open(destination_path, "w:gz") as tar:
        tar.add(dummy_dir, arcname=os.path.basename(dummy_dir))
    logger.info(f"Mock index archive created at {destination_path}")

# --- REAL IMPLEMENTATION ---
def download_index_from_oci(destination_path: Path):
    """
    Downloads the index archive from OCI Object Storage.
    """
    logger.info(f"Attempting to download '{settings.OCI_INDEX_OBJECT_NAME}' from bucket '{settings.OCI_BUCKET_NAME}'...")
    
    try:
        # NOTE: For a real deployment on OCI, instance principal authentication is preferred.
        # This example uses the config file for local/dev compatibility.
        config = oci.config.from_file(settings.OCI_CONFIG_PATH)
        object_storage_client = oci.object_storage.ObjectStorageClient(config)
        
        get_obj = object_storage_client.get_object(
            namespace_name=object_storage_client.get_namespace().data,
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
    """
    Unpacks a .tar.gz archive to the specified directory.
    """
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