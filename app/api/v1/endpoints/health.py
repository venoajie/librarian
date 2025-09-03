# app/api/v1/endpoints/health.py

import asyncio
import logging
import psutil
from fastapi import APIRouter, Request, Response, status as http_status

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
        503: {"description": "Service is in a degraded state (e.g., index not loaded)."},
    }
)
async def get_health(
    request: Request, 
    response: Response,
    ):
    """
    Provides a detailed health status of the service.

    - `status`: "ok" only if the index is fully loaded. Otherwise "degraded".
    - `index_status`: The current state of the ChromaDB index (loading, loaded, not_found).
    - `resource_usage`: System metrics. A failure to collect these metrics will be logged
      but will NOT cause the health check to fail.
    
    Returns HTTP 200 OK if healthy, HTTP 503 Service Unavailable if degraded.
    """
    app_state = request.app.state
    index_status = getattr(app_state, 'index_status', IndexStatus.LOADING)
    service_status = HealthStatus.OK if index_status == IndexStatus.LOADED else HealthStatus.DEGRADED

    if service_status == HealthStatus.DEGRADED:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE

    redis_status = "disconnected"
    if redis_client := request.app.state.redis_client:
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=1.0)
            redis_status = "connected"
        except Exception:
            logger.warning("Health check failed to connect to Redis.")
            
    resource_usage: ResourceUsage
    try:
        cpu_load = psutil.cpu_percent(interval=None)
        memory_info = psutil.virtual_memory()
        resource_usage = ResourceUsage(
            cpu_load_percent=cpu_load,
            memory_usage_percent=memory_info.percent
        )
    except Exception as e:
        logger.warning(f"Could not retrieve resource usage: {e}. This is non-fatal.")
        resource_usage = ResourceUsage(cpu_load_percent=0.0, memory_usage_percent=0.0)

    collection_name = None
    if collection := getattr(app_state, 'chroma_collection', None):
        collection_name = collection.name

    return HealthResponse(
        status=service_status,
        version=request.app.version,
        index_status=index_status,
        redis_status=redis_status, 
        index_last_modified=getattr(app_state, 'index_last_modified', None),
        resource_usage=resource_usage,
        index_branch=settings.OCI_INDEX_BRANCH if index_status == IndexStatus.LOADED else None,
        chroma_collection=collection_name
    )
