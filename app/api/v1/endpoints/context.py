# app\api\v1\endpoints\context.py
import asyncio
import time
import logging
import orjson
import hashlib 
import uuid 
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Tuple

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
    reranker_model = getattr(request.app.state, 'reranker_model', None)

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
                return ContextResponse(
                    query_id=str(uuid.uuid4()), # Generate a new, unique ID
                    context=cached_data['context'],
                    processing_time_ms=int((time.monotonic() - start_time) * 1000)
                )
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
            thread_pool,
            lambda: embedding_model.encode(normalized_query).tolist()
        )
        logger.debug(f"Querying ChromaDB for {log_query_id}...")        
        results = await loop.run_in_executor(
            thread_pool,
            lambda: chroma_collection.query(
                query_embeddings=[query_vector],
                n_results=settings.RERANK_CANDIDATE_POOL_SIZE if reranker_model and settings.RERANKING_ENABLED else body.max_results
                )
            )
        
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        # 2. Rerank results if enabled and available
        if reranker_model and settings.RERANKING_ENABLED and docs:
            logger.info(f"Reranking initial {len(docs)} results for {log_query_id}...")
            rerank_pairs: List[Tuple[str, str]] = [(body.query, doc) for doc in docs]
            
            rerank_scores = await loop.run_in_executor(
                thread_pool,
                lambda: reranker_model.predict(rerank_pairs)
            )
            
            # Combine docs with their new scores and original metadata/distances
            reranked_results = sorted(
                zip(rerank_scores, docs, metadatas, distances), 
                key=lambda x: x[0], 
                reverse=True
            )
            
            # Unzip and slice to the final desired number of results
            final_results = reranked_results[:body.max_results]
            if final_results:
                rerank_scores, docs, metadatas, distances = zip(*final_results)
            else: # Handle case where reranking yields no results
                docs, metadatas, distances = [], [], []
            logger.info(f"Reranking complete. Final result count: {len(docs)}.")


        context_chunks = []
        for i, (doc, meta) in enumerate(zip(docs, metadatas)):
            # Use rerank score if available, otherwise fall back to similarity score
            score = float(rerank_scores[i]) if 'rerank_scores' in locals() else (1.0 - distances[i])
            context_chunks.append(
                ContextChunk(
                    content=doc,
                    metadata=meta,
                    score=score
                )
            )
        
        processing_time_ms = int((time.monotonic() - start_time) * 1000)
        
        response = ContextResponse(
            query_id=str(uuid.uuid4()),
            context=context_chunks,
            processing_time_ms=processing_time_ms
        )

        # 4. Store result in Redis Cache
        try:
            if redis_client and context_chunks:
                payload_to_cache = response.model_dump(exclude={'processing_time_ms', 'query_id'})
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
