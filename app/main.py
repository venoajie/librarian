#  app\main.py

import uvloop
uvloop.install() 

import logging
import asyncio
import sys 
import orjson
import redis.asyncio as redis
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor 
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from datetime import datetime
from sentence_transformers import SentenceTransformer, CrossEncoder
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

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
        # --- Load Models ---
        logger.info("Loading sentence-transformer model into memory...")
        app.state.embedding_model = await loop.run_in_executor(
            thread_pool, lambda: SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        )
        logger.info(f"Model '{settings.EMBEDDING_MODEL_NAME}' loaded successfully.")

        if settings.RERANKING_ENABLED:
            logger.info("Reranking is enabled. Loading CrossEncoder model...")
            try:
                app.state.reranker_model = await loop.run_in_executor(
                    thread_pool, lambda: CrossEncoder(settings.RERANKER_MODEL_NAME)
                )
                logger.info(f"Reranker model '{settings.RERANKER_MODEL_NAME}' loaded successfully.")
            except Exception as e:
                app.state.reranker_model = None
                logger.error(f"Failed to load reranker model: {e}", exc_info=True)
    except Exception as e:
        app.state.embedding_model = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.critical(f"CRITICAL: Failed to load sentence-transformer model: {e}", exc_info=True)
        raise

    try:
        # --- Download Manifest and Connect to DB ---
        logger.info("Downloading index manifest from OCI...")
        manifest = await index_manager.download_manifest_from_oci(thread_pool)
        app.state.index_manifest = manifest
        
        index_model_name = manifest.get("embedding_model")
        if index_model_name != settings.EMBEDDING_MODEL_NAME:
            raise RuntimeError(
                f"FATAL MODEL MISMATCH: Librarian model='{settings.EMBEDDING_MODEL_NAME}', "
                f"Index model='{index_model_name}'. Halting startup."
            )
        logger.info("Index compatibility check passed.")

        db_table_name = manifest.get("db_table_name")
        if not db_table_name:
            raise RuntimeError("Manifest integrity check failed: 'db_table_name' not found.")
        
        app.state.db_table_name = db_table_name
        logger.info(f"Manifest loaded. Using database table: {db_table_name}")

        logger.info("Creating PostgreSQL connection pool...")
        app.state.db_engine = create_async_engine(
            settings.DATABASE_URL, 
            pool_size=10, 
            max_overflow=5,
            pool_recycle=1800 # Recycle connections every 30 mins
        )
        
        async with app.state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        
        logger.info("Database connection successful. Service is now fully operational.")
        app.state.index_status = IndexStatus.LOADED
        app.state.index_last_modified = datetime.utcnow()

    except Exception as e:
        app.state.db_engine = None
        app.state.db_table_name = None
        app.state.index_status = IndexStatus.NOT_FOUND
        logger.error(f"Failed to initialize database connection from manifest: {e}", exc_info=True)
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
    app.state.index_status = IndexStatus.LOADING
    app.state.index_last_modified = None
    app.state.embedding_model = None
    app.state.reranker_model = None
    app.state.db_engine = None
    app.state.db_table_name = None
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
    yield
    
    logger.info("Shutting down Librarian Service.")
    if app.state.redis_client:
        await app.state.redis_client.close()
    if app.state.db_engine:
        await app.state.db_engine.dispose()
    app.state.thread_pool.shutdown()
    logger.info("Shutdown complete.")

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
