# app\core\dependencies.py

import hmac
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from .config import settings

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency to validate the X-API-KEY header."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is missing from X-API-KEY header",
        )

    # Use constant-time comparison to prevent timing attacks.
    # This is the recommended way to compare secrets.
    if not hmac.compare_digest(api_key, settings.LIBRARIAN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
    
    return api_key
