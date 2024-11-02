import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Tuple

import httpx
from fastapi import Depends, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp

import dfh
import dfh.generate
import dfh.k8s
import dfh.routers.auth as auth
import dfh.routers.basic as basic
import dfh.routers.runtimes as runtimes
import dfh.routers.uam as uam
import dfh.watch
from dfh.models import Database, ServerConfig

# Convenience.
logit = logging.getLogger("app")


def isLocalDev() -> bool:
    get = os.environ.get
    return bool(get("PYTEST_VERSION") or get("LOCAL_DEV"))


def make_httpclient() -> Tuple[httpx.AsyncClient, bool]:
    ca_path = os.environ.get("CA_FILE", None)
    verify = str(Path(ca_path).expanduser()) if ca_path else ""
    try:
        client = httpx.AsyncClient(verify=verify)
    except OSError as err:
        logit.error("cannot create http client", {"reason": tuple(err.args)})
        return httpx.AsyncClient(), True
    return client, False


# ----------------------------------------------------------------------
# Setup Server.
# ----------------------------------------------------------------------
def compile_server_config() -> Tuple[ServerConfig, bool]:
    try:
        client, err = make_httpclient()
        assert not err

        cfg = ServerConfig(
            kubeconfig=Path(os.getenv("KUBECONFIG", "")),
            kubecontext=os.getenv("KUBECONTEXT", ""),
            managed_by=os.environ["DFH_MANAGED_BY"],
            env_label=os.environ["DFH_ENV_LABEL"],
            loglevel=os.getenv("DFH_LOGLEVEL", "info"),
            host=os.getenv("DFH_HOST", "0.0.0.0"),
            port=int(os.getenv("DFH_PORT", "5001")),
            httpclient=client,
        )

        return cfg, False
    except (AssertionError, KeyError, ValueError) as e:
        logit.error("missing environment variables", {"names": tuple(e.args)})
        return (
            ServerConfig(
                kubeconfig=Path(""),
                kubecontext="",
                managed_by="",
                env_label="",
                host="",
                port=-1,
                loglevel="",
                httpclient=httpx.AsyncClient(),
            ),
            True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    uam.create_fake_uam_dataset()

    db = app.extra["db"]
    cfg: ServerConfig = app.extra["config"]

    # Provide a single AsyncClient instance to the entire app. This will ensure
    # efficient reuse of sessions, certificates and other common configuration options.
    async with cfg.httpclient:
        # Create Database entry for Namespaces and a watcher.
        tasks = []
        for res in db.resources.values():
            k8scfg, err = dfh.watch.create_cluster_config(
                cfg.kubeconfig, cfg.kubecontext
            )
            assert not err
            tasks.append(
                asyncio.create_task(dfh.watch.setup_k8s_watch(cfg, k8scfg, db, res))
            )

        logit.info("server startup complete")
        yield

        for task in tasks:
            task.cancel()
            await task
    logit.info("server shutdown complete")


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    print(exc.errors())
    print(exc.body)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )


def fetch_secrets() -> Tuple[str, str, bool]:
    return "session-key-from-gsm", "token-key-from-gsm", False


def make_app() -> ASGIApp:
    """Return a fully configured FastAPI instance."""
    cfg, err1 = compile_server_config()
    session_key, token_key, err2 = fetch_secrets()
    if err1 or err2:
        raise RuntimeError("could not meet preconditions to start server")

    app = FastAPI(
        title="Deployments for Humans",
        summary="",
        description="",
        version="0.1.0",
        lifespan=lifespan,
        db={},
        docs_url="/demo/api/docs",
        openapi_url="/demo/api/v1/openapi.json",
        redoc_url="/demo/api/redoc",
    )
    app.extra["session-key"] = session_key
    app.extra["api-token-key"] = token_key
    app.extra["config"] = cfg
    app.extra["db"] = Database()

    # Session middleware to transparently encrypt/decrypt session cookies
    # available via `request.session` inside each handler.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_key,
        max_age=8 * 3600,  # 8 hours
        https_only=False if isLocalDev() else True,
    )

    # Static files of the frontend app.
    app.mount("/demo/static", StaticFiles(directory="static"), name="static")
    app.mount("/demo/assets", StaticFiles(directory="static/assets"), name="assets")

    # Install the web server routes.
    app.include_router(auth.router, prefix="/demo/api/auth", tags=["Authentication"])  # type: ignore
    app.include_router(
        runtimes.router,
        prefix="/demo/api/crt",
        tags=["Runtimes"],
        dependencies=[Depends(auth.is_authenticated)],
    )
    app.include_router(
        uam.router,
        prefix="/demo/api/uam",
        tags=["User Access Management"],
        dependencies=[Depends(auth.is_authenticated)],
    )

    # Basic routes *must* come last because one of them will serve the
    # frontend on all hitherto undefined routes.
    app.include_router(basic.router, prefix="", tags=["Basic"])

    # Install the exception handlers.
    app.add_exception_handler(RequestValidationError, handler=validation_error_handler)  # type: ignore

    # Include helper endpoints if we are running tests only.
    # NOTE: these routes *must not* be included in any deployed version. The
    # Dockerfile contains an additional safeguard.
    if isLocalDev():  # codecov-skip
        import dfh.routers.testing as testing

        app.include_router(testing.router, tags=["Testing"])

    return app
