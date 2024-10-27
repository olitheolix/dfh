"""A simple Hello World web server that can return arbitrary environment variables."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse, PlainTextResponse

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
    db={},
)


@app.get("/")
def read_root() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_200_OK, content={"Hello": "World"})


@app.get("/healthz")
def get_healthz() -> int:
    return status.HTTP_200_OK


@app.get("/envvar/{name}")
def get_envvar(name: str) -> PlainTextResponse:
    value = os.getenv(name, "<undefined>")
    resp = f"Environment Variable: {name}={value}\n"
    return PlainTextResponse(status_code=status.HTTP_200_OK, content=resp)
