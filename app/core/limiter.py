# app\core\limiter.py

from slowapi import Limiter
from slowapi.util import get_remote_address
from .config import settings

# Create the single, shared limiter instance.
# It is configured from the settings file and will be imported by other parts of the app.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED
)