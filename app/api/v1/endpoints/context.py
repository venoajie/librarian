# app\api\v1\endpoints\context.py

import asyncio
import time
import logging
import orjson
import hashlib 
from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.models.schemas import ContextRequest, ContextResponse, ContextChunk
from app.core.dependencies import get_api_key
from app.core.config import settings
from app.core.limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Retrieve Codebase Context",
    tags=["Core"]
)
@limiter.limit(settings.RATE_LIMIT_TIMEFRAME)
async def get_context(
    request: Request,
    body: ContextRequest,
    api_key: str = Depends(get_api_key)
):
    """Retrieves relevant context chunks for a given query from the codebase index."""
    start_time = time.monotonic()
    
    normalized_query = body.query.lower().strip()
    query_hash = hashlib.md5(normalized_query.encode()).hexdigest()
    log_query_id = f"query_hash:{query_hash[:8]}" # For concise logging
    cache_key = f"context_query:{query_hash}:{body.max_results}"

    redis_client = request.app.state.redis_client
    chroma_collection = request.app.state.chroma_collection
    embedding_model = request.app.state.embedding_model

    if not embedding_model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding model is not available. Service is in a degraded state."
        )

    # 1. Check Redis Cache
    try:
        if redis_client:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {log_query_id}")
                cached_data = orjson.loads(cached_result)
                cached_data['processing_time_ms'] = int((time.monotonic() - start_time) * 1000)
                return ContextResponse(**cached_data)
    except Exception as e:
        logger.error(f"Redis cache check failed for {log_query_id}: {e}", exc_info=True)

    logger.info(f"Cache miss for {log_query_id}")

    if not chroma_collection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Index is not loaded or available. Please try again later."
        )

    try:
        logger.debug(f"Encoding query for {log_query_id}...")
        loop = asyncio.get_running_loop()
        thread_pool = request.app.state.thread_pool
        query_vector = await loop.run_in_executor(
            thread_pool,  # Use the bounded pool
            lambda: embedding_model.encode(normalized_query).tolist()
        )
        logger.debug(f"Querying ChromaDB for {log_query_id}...")        
        results = await loop.run_in_executor(
            thread_pool,
            lambda: chroma_collection.query(
                query_embeddings=[query_vector],
                n_results=body.max_results
                )
            )
        
        context_chunks = []
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        for doc, meta, dist in zip(docs, metadatas, distances):
            context_chunks.append(
                ContextChunk(
                    content=doc,
                    metadata=meta,
                    score=1.0 - dist
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
                logger.info(f"Stored new cache entry for {log_query_id}")
        except Exception as e:
            logger.error(f"Redis cache store failed for {log_query_id}: {e}", exc_info=True)

        return response

    except Exception as e:
        logger.error(f"Error querying ChromaDB for {log_query_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while querying the index."
        )