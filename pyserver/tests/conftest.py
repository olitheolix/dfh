from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from square.dtypes import K8sConfig

import dfh.api
import dfh.logstreams
import dfh.watch
from dfh.models import Database, ServerConfig


def pytest_configure(*args, **kwargs):
    """Pytest calls this hook on startup."""
    # Set log level to DEBUG for all unit tests.
    dfh.logstreams.setup("DEBUG")


def get_server_config():
    return ServerConfig(
        kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
        kubecontext="kind-kind",
        managed_by="dfh",
        env_label="env",
        host="0.0.0.0",
        port=5001,
        loglevel="info",
    )


@pytest.fixture
async def realK8sCfg():
    """Return an async test client."""
    cfg = get_server_config()
    k8scfg, err = dfh.watch.create_cluster_config(cfg.kubeconfig, cfg.kubecontext)
    assert not err
    yield k8scfg


@pytest.fixture
async def k8scfg(respx_mock):
    """Return an async test client."""
    async with AsyncClient(base_url="https:") as client:
        yield K8sConfig(client=client)


@pytest.fixture
async def clientls():
    with TestClient(dfh.api.app) as client:
        yield client


@pytest.fixture
async def client():
    c = TestClient(dfh.api.app)
    c.app.extra = {  # type: ignore
        "db": Database(),
        "config": get_server_config(),
    }
    yield c
