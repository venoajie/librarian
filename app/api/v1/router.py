#app\api\v1\router.py

from fastapi import APIRouter
from .endpoints import health, context

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(context.router)
