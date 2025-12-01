# api/auth.py
from fastapi import Header, HTTPException, Security
import os
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY")
APIKEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=APIKEY_NAME, auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    """
    Validate the API key from the request header.

    FastAPI dependency that extracts and validates the API key from the
    X-API-Key header. Raises appropriate HTTP exceptions for missing or
    invalid keys.

    Args:
        api_key_header (str): API key extracted from X-API-Key header via
            Security dependency injection

    Returns:
        str: The validated API key

    Raises:
        HTTPException: 401 if API key header is missing
        HTTPException: 403 if API key is present but doesn't match API_KEY

    Note:
        Used as a FastAPI dependency via Depends() to protect endpoints.
        Compares against the API_KEY constant from configuration.
    """
    if not api_key_header:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if api_key_header != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return api_key_header
