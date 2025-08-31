#  app\main.py

import uvloop
uvloop.install() 

import logging
import redis.asyncio as redis
import chromadb
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter
from app.core.config import settings
from app.api.v1.router import api_router
from app.models.schemas import IndexStatus
from app.core import index_manager

# --- Setup Logging ---
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info(f"Starting Librarian Service v{settings.SERVICE_VERSION}")
    
    # --- Initialize State ---
    app.state.index_status = IndexStatus.LOADING
    app.state.index_last_modified = None
    
    # --- Initialize Redis Client ---
    try:
        app.state.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await app.state.redis_client.ping()
        logger.info("Successfully connected to Redis.")
    except Exception as e:
        app.state.redis_client = None
        logger.error(f"Could not connect to Redis: {e}", exc_info=True)

    # --- Load Sentence Transformer Model ---
    try:
        logger.info("Loading sentence-transformer model into memory...")
        model_name = "all-MiniLM-L6-v2" 
        app.state.embedding_model = SentenceTransformer(model_name)
        logger.info(f"Model '{model_name}' loaded successfully.")
    except Exception as e:
        app.state.embedding_model = None
        logger.critical(f"CRITICAL: Failed to load sentence-transformer model: {e}", exc_info=True)

    # --- Load ChromaDB Index ---
    archive_path = Path("/tmp/index.tar.gz")
    index_path = Path(settings.CHROMA_DB_PATH)
    
    #index_manager._mock_oci_download(archive_path)
    downloaded =  index_manager.download_index_from_oci(archive_path)

    if downloaded and index_manager.unpack_index(archive_path, index_path):
        try:
            chroma_client = chromadb.PersistentClient(path=str(index_path))
            app.state.chroma_collection = chroma_client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
            
            app.state.index_status = IndexStatus.LOADED
            app.state.index_last_modified = datetime.utcnow()
            logger.info(f"ChromaDB index '{settings.CHROMA_COLLECTION_NAME}' loaded successfully.")
        except Exception as e:
            app.state.chroma_collection = None
            app.state.index_status = IndexStatus.NOT_FOUND
            logger.error(f"Failed to load ChromaDB collection: {e}", exc_info=True)
    else:
        app.state.chroma_collection = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.error("Index setup failed due to download or unpacking error.")

    yield
    
    # --- Shutdown ---
    logger.info("Shutting down Librarian Service.")
    if app.state.redis_client:
        await app.state.redis_client.close()
        logger.info("Redis connection closed.")

app = FastAPI(
    title="Librarian RAG Service",
    description="A centralized service for retrieving codebase context.",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    default_response_class=ORJSONResponse,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_router, prefix="/api/v1")

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Welcome to the Librarian RAG Service. See /api/docs for details."}
