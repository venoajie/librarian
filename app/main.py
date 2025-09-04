#  app\main.py

import uvloop
uvloop.install() 

import logging
import asyncio
import sys 
import orjson
import redis.asyncio as redis
import chromadb
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor 
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer, CrossEncoder
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter
from app.core.config import settings
from app.api.v1.router import api_router
from app.models.schemas import IndexStatus
from app.core import index_manager

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def _handle_startup_errors(task: asyncio.Task) -> None:
    """Callback to handle exceptions in the background startup task."""
    try:
        task.result()
    except Exception as e:
        logger.critical(
            f"FATAL: Background initialization failed: {e}. Application will shut down.",
            exc_info=True
        )
        sys.exit(1)

async def load_dependencies(app: FastAPI):
    logger.info("Background task started: Loading dependencies...")
    loop = asyncio.get_running_loop()
    thread_pool = app.state.thread_pool

    try:
        # --- Load Embedding Model ---
        logger.info("Loading sentence-transformer model into memory...")
        model_name = settings.EMBEDDING_MODEL_NAME
        app.state.embedding_model = await loop.run_in_executor(
            thread_pool, lambda: SentenceTransformer(model_name)
        )
        logger.info(f"Model '{model_name}' loaded successfully.")

        # --- Load Reranker Model (if enabled) ---
        if settings.RERANKING_ENABLED:
            logger.info("Reranking is enabled. Loading CrossEncoder model...")
            reranker_model_name = settings.RERANKER_MODEL_NAME
            try:
                app.state.reranker_model = await loop.run_in_executor(
                    thread_pool, lambda: CrossEncoder(reranker_model_name)
                )
                logger.info(f"Reranker model '{reranker_model_name}' loaded successfully.")
            except Exception as e:
                app.state.reranker_model = None
                logger.error(f"Failed to load reranker model '{reranker_model_name}': {e}", exc_info=True)
                # Do not raise; the service can run in a degraded state without the reranker.
        else:
            logger.info("Reranking is disabled by configuration.")

    except Exception as e:
        app.state.embedding_model = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.critical(f"CRITICAL: Failed to load sentence-transformer model: {e}", exc_info=True)
        raise

    archive_path = Path("/tmp/index.tar.gz")
    index_path = Path(settings.CHROMA_DB_PATH)
    
    try:
        downloaded = await loop.run_in_executor(
            thread_pool, index_manager.download_index_from_oci, archive_path
        )

        if downloaded and await loop.run_in_executor(
            thread_pool, index_manager.unpack_index, archive_path, index_path
        ):
            manifest_path = index_path / "index_manifest.json"
            if not manifest_path.exists():
                raise RuntimeError("Index integrity check failed: index_manifest.json not found in the unpacked archive.")
            
            manifest_content = manifest_path.read_bytes()
            manifest = orjson.loads(manifest_content)
            
            app.state.index_manifest = manifest
            
            index_model_name = manifest.get("embedding_model")
            librarian_model_name = settings.EMBEDDING_MODEL_NAME

            logger.info(
                f"Verifying index compatibility: "
                f"Librarian model='{librarian_model_name}', "
                f"Index model='{index_model_name}'"
            )

            if index_model_name != librarian_model_name:
                raise RuntimeError(
                    f"FATAL MODEL MISMATCH: The Librarian is configured to use '{librarian_model_name}', "
                    f"but the downloaded index was built with '{index_model_name}'. Halting startup."
                )
            logger.info("Index compatibility check passed.")

            collection_name_from_manifest = manifest.get("chroma_collection_name")
            if not collection_name_from_manifest:
                raise RuntimeError("Index integrity check failed: 'chroma_collection_name' not found in manifest.")

            chroma_client = await loop.run_in_executor(
                thread_pool, lambda: chromadb.PersistentClient(path=str(index_path))
            )

            logger.info(f"Attempting to load ChromaDB collection from manifest: {collection_name_from_manifest}")

            app.state.chroma_collection = await loop.run_in_executor(
                thread_pool, lambda: chroma_client.get_collection(
                    name=collection_name_from_manifest,
                )
            )

            app.state.index_status = IndexStatus.LOADED
            app.state.index_last_modified = datetime.utcnow()            
            logger.info(f"ChromaDB index '{collection_name_from_manifest}' loaded successfully. Service is now fully operational.")
        else:
            app.state.chroma_collection = None
            app.state.index_status = IndexStatus.NOT_FOUND
            logger.error("Index setup failed due to download or unpacking error.")
            raise RuntimeError("Failed to download or unpack the index from OCI.")
    except Exception as e:
        app.state.chroma_collection = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.error(f"Failed to load ChromaDB collection: {e}", exc_info=True)
        raise

async def timed_load_wrapper(app: FastAPI):
    """Wraps the dependency loader with a timeout."""
    try:
        await asyncio.wait_for(
            load_dependencies(app), 
            timeout=settings.STARTUP_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.critical(
            f"FATAL: Dependency loading timed out after {settings.STARTUP_TIMEOUT_SECONDS} seconds. Application will shut down."
        )
        raise
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Librarian Service v{settings.SERVICE_VERSION}")
    
    app.state.thread_pool = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
    logger.info(f"Initialized bounded thread pool with {settings.MAX_WORKERS} workers.")

    app.state.index_status = IndexStatus.LOADING
    app.state.index_last_modified = None
    app.state.embedding_model = None
    app.state.reranker_model = None
    app.state.chroma_collection = None
    app.state.index_manifest = None
    
    try:
        app.state.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await app.state.redis_client.ping()
        logger.info("Successfully connected to Redis.")
    except Exception as e:
        app.state.redis_client = None
        logger.error(f"Could not connect to Redis: {e}", exc_info=True)

    startup_task = asyncio.create_task(timed_load_wrapper(app))
    startup_task.add_done_callback(_handle_startup_errors)
    
    logger.info("Application startup complete. Now listening for requests.")
    logger.info("Index and model loading will continue in the background.")
    yield
    
    logger.info("Shutting down Librarian Service.")
    if app.state.redis_client:
        await app.state.redis_client.close()
        logger.info("Redis connection closed.")
    
    app.state.thread_pool.shutdown()
    logger.info("Thread pool shut down.")

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