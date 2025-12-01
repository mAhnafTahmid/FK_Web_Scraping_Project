# api/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi import FastAPI

limiter = Limiter(key_func=get_remote_address)


def register_rate_limit(app: FastAPI):
    """
    Register rate limiting middleware and exception handler to the FastAPI app.

    Attaches the slowapi limiter to the application state and configures a
    custom exception handler for 429 Too Many Requests responses.

    Args:
        app (FastAPI): The FastAPI application instance to configure

    Returns:
        None

    Side Effects:
        - Sets app.state.limiter to the configured limiter instance
        - Registers custom handler for 429 status code exceptions

    Note:
        Must be called during application initialization before adding routes.
        The limiter and handler are defined elsewhere in the module.
    """
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)
