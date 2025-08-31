# app\api\v1\endpoints\context.py

import asyncio
import time
import logging
import orjson
from fastapi import APIRouter, Depends, HTTPException, status, Request
from app.models.schemas import ContextRequest, ContextResponse, ContextChunk
from app.core.dependencies import get_api_key
from app.core.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Retrieve Codebase Context",
    tags=["Core"]
)
@limiter.limit(settings.RATE_LIMIT_TIMEFRAME, on_breach=lambda scope: scope.app.state.limiter.on_breach(scope))
async def get_context(
    request: Request,
    body: ContextRequest,
    api_key: str = Depends(get_api_key)
):
    """Retrieves relevant context chunks for a given query from the codebase index."""
    start_time = time.monotonic()
    
    # Get clients from application state
    redis_client = request.app.state.redis_client
    chroma_collection = request.app.state.chroma_collection

    # Get the embedding model from application state
    embedding_model = request.app.state.embedding_model
    if not embedding_model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding model is not available. Service is in a degraded state."
        )

    # 1. Check Redis Cache
    cache_key = f"context_query:{body.query}:{body.max_results}"
    try:
        if redis_client:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for query: '{body.query[:50]}...'")
                cached_data = orjson.loads(cached_result)
                cached_data['processing_time_ms'] = int((time.monotonic() - start_time) * 1000)
                return ContextResponse(**cached_data)
    except Exception as e:
        logger.error(f"Redis cache check failed: {e}", exc_info=True)
        # Non-blocking error: proceed without cache

    logger.info(f"Cache miss for query: '{body.query[:50]}...'")

    # 2. Query ChromaDB
    if not chroma_collection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Index is not loaded or available. Please try again later."
        )

    try:
        logger.debug("Encoding query text into a vector...")
        loop = asyncio.get_running_loop()
        query_vector = await loop.run_in_executor(
            None,  # Use the default thread pool executor
            lambda: embedding_model.encode(body.query).tolist()
        )
        logger.debug(f"Querying ChromaDB collection '{settings.CHROMA_COLLECTION_NAME}' with vector...")
        results = chroma_collection.query(
            query_embeddings=[query_vector], # USE THE VECTOR, NOT THE TEXT
            n_results=body.max_results
        )        
        
        # 3. Format the response
        context_chunks = []
        # Results are lists of lists because we can query multiple texts at once. We only query one.
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        for doc, meta, dist in zip(docs, metadatas, distances):
            context_chunks.append(
                ContextChunk(
                    content=doc,
                    metadata=meta,
                    score=1.0 - dist  # Convert distance to similarity score
                )
            )
        
        processing_time_ms = int((time.monotonic() - start_time) * 1000)
        response = ContextResponse(
            context=context_chunks,
            processing_time_ms=processing_time_ms
        )

        # 4. Store result in Redis Cache
        try:
            if redis_client:
                payload_to_cache = response.model_dump(exclude={'processing_time_ms'})
                await redis_client.set(
                    cache_key,
                    orjson.dumps(payload_to_cache),
                    ex=settings.REDIS_CACHE_TTL_SECONDS
                )
                logger.info(f"Stored new cache entry for query: '{body.query[:50]}...'")
        except Exception as e:
            logger.error(f"Redis cache store failed: {e}", exc_info=True)
            # Non-blocking error

        return response

    except Exception as e:
        logger.error(f"Error querying ChromaDB: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while querying the index."
        )
