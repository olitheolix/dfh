from fastapi import Request
from typing import cast
from dfh.models import ServerConfig


def get_config(request: Request) -> ServerConfig:
    """FastAPI dependency to extract the server config."""
    return cast(ServerConfig, request.app.extra["config"])
