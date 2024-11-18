from pathlib import Path

import httpx
import pytest
from google.cloud.spanner_admin_database_v1.types import spanner_database_admin
from httpx import AsyncClient
from square.dtypes import K8sConfig

import dfh.api
import dfh.logstreams
import dfh.routers.dependencies as deps
import dfh.watch
from dfh.models import ServerConfig


def pytest_configure(*args, **kwargs):
    """Pytest calls this hook on startup."""
    # Set log level to DEBUG for all unit tests.
    dfh.logstreams.setup("DEBUG")

    create_spanner_tables()


def get_server_config():
    return ServerConfig(
        kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
        kubecontext="kind-kind",
        managed_by="dfh",
        env_label="env",
        host="0.0.0.0",
        port=5001,
        loglevel="info",
        httpclient=httpx.AsyncClient(),
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


def create_spanner_tables():
    client, database, instance_id, err = deps.create_spanner_client()
    assert not err and client and database

    # Drop the database
    database_path = client.database_admin_api.database_path(
        "my-project", "my-instance", "my-database"
    )
    request = spanner_database_admin.DropDatabaseRequest(database=database_path)
    client.database_admin_api.drop_database(request=request)

    assert not database.exists()

    request = spanner_database_admin.CreateDatabaseRequest(
        parent=client.database_admin_api.instance_path(client.project, instance_id),
        create_statement=f"CREATE DATABASE `{database.database_id}`",
        extra_statements=[
            """
        CREATE TABLE OrgUsers (
            email STRING(128) NOT NULL,
            name STRING(128) NOT NULL,
            lanid STRING(128) NOT NULL,
            slack STRING(128) NOT NULL,
            role STRING(128) NOT NULL,
            manager STRING(128) NOT NULL,
        ) PRIMARY KEY (email)
        """,
            """
        CREATE TABLE OrgGroups (
            email STRING(128) NOT NULL,
            owner STRING(128) NOT NULL,
            provider STRING(128) NOT NULL,
            description STRING(1024) NOT NULL,
        ) PRIMARY KEY (email)
        """,
            """
        CREATE TABLE OrgGroupsUsers (
            group_id STRING(128) NOT NULL,
            user_id STRING(128) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES OrgUsers(email) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES OrgGroups(email) ON DELETE CASCADE
        ) PRIMARY KEY (group_id, user_id)
        """,
            """
        CREATE TABLE OrgGroupsGroups (
            parent_id STRING(128) NOT NULL,
            child_id STRING(128) NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES OrgGroups(email) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES OrgGroups(email) ON DELETE CASCADE
        ) PRIMARY KEY (parent_id, child_id)
        """,
            """
        CREATE TABLE OrgGroupsRoles (
            group_id STRING(128) NOT NULL,
            roles ARRAY<STRING(MAX)>,
            FOREIGN KEY (group_id) REFERENCES OrgGroups(email) ON DELETE CASCADE
        ) PRIMARY KEY (group_id)
        """,
            """
        CREATE TABLE OrgRootUsers (
            email STRING(128) NOT NULL,
        ) PRIMARY KEY (email)
        """,
        ],
    )

    operation = client.database_admin_api.create_database(request=request)
    operation.result()
