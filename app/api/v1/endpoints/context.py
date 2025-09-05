# app\api\v1\endpoints\context.py

import asyncio
import time
import logging
import orjson
import hashlib 
import uuid 
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Tuple
from sqlalchemy import text

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
async def get_context(request: Request, body: ContextRequest, api_key: str = Depends(get_api_key)):
    """
    Retrieves relevant context chunks for a given query from PostgreSQL.
    """
    start_time = time.monotonic()
    
    normalized_query = body.query.lower().strip()
    cache_key_parts = [normalized_query, str(body.max_results)]
    if body.filters:
        sorted_filters = orjson.dumps(body.filters, option=orjson.OPT_SORT_KEYS).decode()
        cache_key_parts.append(sorted_filters)
    
    cache_key_string = ":".join(cache_key_parts)
    query_hash = hashlib.md5(cache_key_string.encode()).hexdigest()
    log_query_id = f"query_hash:{query_hash[:8]}"
    cache_key = f"context_query:{query_hash}"

    redis_client = request.app.state.redis_client
    db_engine = request.app.state.db_engine
    db_table_name = request.app.state.db_table_name
    embedding_model = request.app.state.embedding_model
    reranker_model = getattr(request.app.state, 'reranker_model', None)

    if not embedding_model:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding model is not available.")

    # 1. Check Redis Cache
    if redis_client:
        try:
            if cached_result := await redis_client.get(cache_key):
                logger.info(f"Cache hit for {log_query_id}")
                cached_data = orjson.loads(cached_result)
                return ContextResponse(query_id=str(uuid.uuid4()), **cached_data)
        except Exception as e:
            logger.error(f"Redis cache check failed for {log_query_id}: {e}", exc_info=True)

    logger.info(f"Cache miss for {log_query_id} with filters: {body.filters}")

    if not db_engine or not db_table_name:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database connection is not available.")

    try:
        loop = asyncio.get_running_loop()
        thread_pool = request.app.state.thread_pool
        query_vector = await loop.run_in_executor(
            thread_pool, lambda: embedding_model.encode(normalized_query).tolist()
        )
        
        n_results_retrieval = settings.RERANK_CANDIDATE_POOL_SIZE if reranker_model and settings.RERANKING_ENABLED else body.max_results
        
        # --- Build SQL Query Securely with Parameterization ---
        params = {'query_vector': query_vector, 'limit': n_results_retrieval}
        where_clauses = []
        if body.filters:
            for i, (key, value) in enumerate(body.filters.items()):
                param_name = f"filter_val_{i}"
                # This creates a clause like "metadata->>'language' = :filter_val_0"
                # The value is passed separately in `params`, preventing SQL injection.
                where_clauses.append(f"metadata->>'{key}' = :{param_name}")
                params[param_name] = str(value)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql_query = text(f"""
            SELECT id, content, metadata, 1 - (embedding <-> :query_vector) AS score
            FROM {db_table_name}
            {where_sql}
            ORDER BY score DESC
            LIMIT :limit
        """)

        async with db_engine.connect() as conn:
            result = await conn.execute(sql_query, params)
            rows = result.fetchall()

        docs, metadatas, scores = ([row.content for row in rows], [row.metadata for row in rows], [row.score for row in rows])

        # 2. Rerank results if enabled
        if reranker_model and settings.RERANKING_ENABLED and docs:
            logger.info(f"Reranking initial {len(docs)} results for {log_query_id}...")
            rerank_pairs: List[Tuple[str, str]] = [(body.query, doc) for doc in docs]
            rerank_scores = await loop.run_in_executor(thread_pool, lambda: reranker_model.predict(rerank_pairs))
            
            reranked_results = sorted(zip(rerank_scores, docs, metadatas), key=lambda x: x[0], reverse=True)
            final_results = reranked_results[:body.max_results]
            final_scores, final_docs, final_metadatas = (zip(*final_results) if final_results else ([], [], []))
        else:
            final_docs, final_metadatas, final_scores = docs, metadatas, scores

        # 3. Format and cache the final response
        context_chunks = [ContextChunk(content=doc, metadata=meta, score=float(score)) for doc, meta, score in zip(final_docs, final_metadatas, final_scores)]
        
        response_data = {
            "context": context_chunks,
            "processing_time_ms": int((time.monotonic() - start_time) * 1000)
        }

        if redis_client and context_chunks:
            try:
                await redis_client.set(cache_key, orjson.dumps(response_data), ex=settings.REDIS_CACHE_TTL_SECONDS)
                logger.info(f"Stored new cache entry for {log_query_id}")
            except Exception as e:
                logger.error(f"Redis cache store failed for {log_query_id}: {e}", exc_info=True)

        return ContextResponse(query_id=str(uuid.uuid4()), **response_data)

    except Exception as e:
        logger.error(f"Error processing context request for {log_query_id}: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "An internal error occurred.")
