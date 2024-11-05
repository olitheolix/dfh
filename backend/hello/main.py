"""A simple Hello World web server that can return arbitrary environment variables."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.responses import PlainTextResponse

# Convenience.
logit = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logit.info("server startup complete")
    yield
    logit.info("server shutdown complete")


app = FastAPI(
    lifespan=lifespan,
    title="Hello World",
    summary="",
    description="",
    version="0.1.0",
)


@app.get("/healthz")
def get_healthz() -> int:
    return status.HTTP_200_OK


@app.get("/{path:path}", include_in_schema=False)
def get_envvar(path: str) -> PlainTextResponse:
    # Extract the last two path elements.
    # Example: /foo/bar/blah/x/y -> (x, y)
    p = Path(path)
    code, name = p.parent.name, p.name

    # Return a default message unless the second last path argument spells `envvar`.
    if code != "envvar":
        return PlainTextResponse(status_code=status.HTTP_200_OK, content="hello world")

    # Fetch the desired environment variable and return its value.
    value = os.getenv(name, "<undefined>")
    resp = f"Environment Variable: {name}={value}\n"
    return PlainTextResponse(status_code=status.HTTP_200_OK, content=resp)
