# app/api/v1/endpoints/health.py

import asyncio
import logging
import psutil
from fastapi import APIRouter, Request, Response, status as http_status
from sqlalchemy import text

from app.models.schemas import HealthResponse, HealthStatus, IndexStatus, ResourceUsage
from app.core.config import settings 

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Get Service Health",
    tags=["Monitoring"],
    responses={
        200: {"description": "Service is operational."},
        503: {"description": "Service is in a degraded state."},
    }
)
async def get_health(request: Request, response: Response):
    """
    Provides a detailed health status of the service, including database and model status.
    """
    app_state = request.app.state
    index_status = getattr(app_state, 'index_status', IndexStatus.LOADING)

    # Check Reranker Status
    reranker_status = "disabled"
    is_reranker_healthy = True
    if settings.RERANKING_ENABLED:
        reranker_status = "loaded" if getattr(app_state, 'reranker_model', None) else "error"
        if reranker_status == "error":
            is_reranker_healthy = False

    # Check Database Status
    db_status = "disconnected"
    is_db_healthy = False
    if db_engine := app_state.db_engine:
        try:
            async with db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "connected"
            is_db_healthy = True
        except Exception:
            logger.warning("Health check failed to connect to database.")

    # Determine Overall Service Status
    service_status = HealthStatus.OK if index_status == IndexStatus.LOADED and is_reranker_healthy and is_db_healthy else HealthStatus.DEGRADED
    if service_status == HealthStatus.DEGRADED:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Redis Status
    redis_status = "disconnected"
    if redis_client := request.app.state.redis_client:
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=1.0)
            redis_status = "connected"
        except Exception:
            logger.warning("Health check failed to connect to Redis.")
            
    # Get Resource Usage
    try:
        cpu_load = psutil.cpu_percent(interval=None)
        memory_info = psutil.virtual_memory()
        resource_usage = ResourceUsage(cpu_load_percent=cpu_load, memory_usage_percent=memory_info.percent)
    except Exception as e:
        logger.warning(f"Could not retrieve resource usage: {e}. This is non-fatal.")
        resource_usage = ResourceUsage(cpu_load_percent=0.0, memory_usage_percent=0.0)

    index_branch = None
    if manifest := getattr(app_state, 'index_manifest', None):
        index_branch = manifest.get("branch")
    
    return HealthResponse(
        status=service_status,
        version=request.app.version,
        index_status=index_status,
        db_status=db_status,
        redis_status=redis_status, 
        reranker_status=reranker_status,
        index_last_modified=getattr(app_state, 'index_last_modified', None),
        resource_usage=resource_usage,
        index_branch=index_branch,
        db_table_name=getattr(app_state, 'db_table_name', None)
    )
