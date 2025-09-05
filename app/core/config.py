#app\core\config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, root_validator, model_validator
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

    # Service Performance
    MAX_WORKERS: int = Field(4, env="MAX_WORKERS")
      
    EMBEDDING_MODEL_NAME: str = Field("BAAI/bge-large-en-v1.5", env="EMBEDDING_MODEL_NAME")
    STARTUP_TIMEOUT_SECONDS: int = Field(300, env="STARTUP_TIMEOUT_SECONDS")
    
    # --- Reranking Configuration ---
    RERANKING_ENABLED: bool = Field(True, env="RERANKING_ENABLED")
    RERANKER_MODEL_NAME: str = Field("cross-encoder/ms-marco-MiniLM-L-6-v2", env="RERANKER_MODEL_NAME")
    RERANK_CANDIDATE_POOL_SIZE: int = Field(
        25, 
        gt=0, 
        description="Number of initial candidates to retrieve from vector search for reranking."
    )
    
    # API Authentication (supports Docker secrets)
    LIBRARIAN_API_KEY: Optional[str] = Field(None, env="LIBRARIAN_API_KEY")
    LIBRARIAN_API_KEY_FILE: Optional[str] = Field(None, env="LIBRARIAN_API_KEY_FILE")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_TIMEFRAME: str = Field("100/minute", env="RATE_LIMIT_TIMEFRAME")

    # OCI Object Storage
    OCI_CONFIG_PATH: Optional[str] = Field(None, env="OCI_CONFIG_PATH")
    OCI_BUCKET_NAME: str = Field(..., env="OCI_BUCKET_NAME")
    OCI_PROJECT_NAME: str = Field(..., env="OCI_PROJECT_NAME")
    OCI_INDEX_BRANCH: str = Field(..., env="OCI_INDEX_BRANCH")
    OCI_INDEX_OBJECT_NAME: Optional[str] = None # This will be derived

    # PostgreSQL Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # Redis Cache
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    REDIS_CACHE_TTL_SECONDS: int = Field(3600, env="REDIS_CACHE_TTL_SECONDS")

    @root_validator(pre=False, skip_on_failure=True)
    def process_derived_settings(cls, values):
        """
        Load secrets from files and derive dynamic configuration values after initial load.
        """
        api_key_file = values.get("LIBRARIAN_API_KEY_FILE")
        if api_key_file:
            try:
                with open(api_key_file, 'r') as f:
                    values["LIBRARIAN_API_KEY"] = f.read().strip()
            except IOError:
                raise ValueError(f"Could not read API key from file: {api_key_file}")
        
        if not values.get("LIBRARIAN_API_KEY"):
            raise ValueError("LIBRARIAN_API_KEY must be set, either via environment variable or LIBRARIAN_API_KEY_FILE.")
            
        project = values.get("OCI_PROJECT_NAME")
        branch = values.get("OCI_INDEX_BRANCH")            
        if project and branch:
            values["OCI_INDEX_OBJECT_NAME"] = f"indexes/{project}/{branch}/latest/index_manifest.json"
        else:
            raise ValueError("OCI_PROJECT_NAME and OCI_INDEX_BRANCH must be set to derive the object name.")
            
        return values

    @model_validator(mode='after')
    def validate_reranking_pool(self) -> 'Settings':
        if self.RERANKING_ENABLED and self.RERANK_CANDIDATE_POOL_SIZE < 5:
            raise ValueError("RERANK_CANDIDATE_POOL_SIZE must be at least 5 when reranking is enabled.")
        return self

settings = Settings()
