#app\core\config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator, root_validator
from typing import Optional

class Settings(BaseSettings):
    """Librarian Service Configuration loaded from environment variables and secrets."""
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore",
        )

    # Service Metadata
    SERVICE_VERSION: str = Field("1.0.0", env="SERVICE_VERSION")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # API Authentication (supports Docker secrets)
    LIBRARIAN_API_KEY: Optional[str] = Field(None, env="LIBRARIAN_API_KEY")
    LIBRARIAN_API_KEY_FILE: Optional[str] = Field(None, env="LIBRARIAN_API_KEY_FILE")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_TIMEFRAME: str = Field("100/minute", env="RATE_LIMIT_TIMEFRAME")

    # OCI Object Storage
    OCI_CONFIG_PATH: str = Field("/home/appuser/.oci/config", env="OCI_CONFIG_PATH")
    OCI_BUCKET_NAME: str = Field(..., env="OCI_BUCKET_NAME")
    OCI_INDEX_OBJECT_NAME: str = Field("index.tar.gz", env="OCI_INDEX_OBJECT_NAME")

    # ChromaDB
    CHROMA_DB_PATH: str = Field("/data/chroma", env="CHROMA_DB_PATH")
    CHROMA_COLLECTION_NAME: str = Field("codebase_collection", env="CHROMA_COLLECTION_NAME")

    # Redis Cache
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    REDIS_CACHE_TTL_SECONDS: int = Field(3600, env="REDIS_CACHE_TTL_SECONDS")

    @root_validator(pre=False, skip_on_failure=True)
    def load_api_key_from_file(cls, values):
        """Load API key from file if specified, providing a secure way to handle secrets."""
        api_key_file = values.get("LIBRARIAN_API_KEY_FILE")
        api_key = values.get("LIBRARIAN_API_KEY")

        if api_key_file:
            try:
                with open(api_key_file, 'r') as f:
                    values["LIBRARIAN_API_KEY"] = f.read().strip()
            except IOError:
                raise ValueError(f"Could not read API key from file: {api_key_file}")
        
        if not values.get("LIBRARIAN_API_KEY"):
            raise ValueError("LIBRARIAN_API_KEY must be set, either via environment variable or LIBRARIAN_API_KEY_FILE.")
            
        return values

settings = Settings()