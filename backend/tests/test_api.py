from pathlib import Path
from typing import cast
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import dfh.api
import dfh.k8s


class TestBasic:
    def test_islocaldev(self):
        with mock.patch.dict("os.environ", values={}, clear=True):
            assert not dfh.api.isLocalDev()

        new_env = {"PYTEST_VERSION": "1", "LOCAL_DEV": "1"}
        with mock.patch.dict("os.environ", values=new_env, clear=True):
            assert dfh.api.isLocalDev()

        new_env = {"PYTEST_VERSION": "1"}
        with mock.patch.dict("os.environ", values=new_env, clear=True):
            assert dfh.api.isLocalDev()

        new_env = {"LOCAL_DEV": "1"}
        with mock.patch.dict("os.environ", values=new_env, clear=True):
            assert dfh.api.isLocalDev()


class TestConfiguration:
    def test_compile_server_config_ok(self, tmp_path: Path):
        gsecrets = tmp_path / "google-client-secrets.json"
        gsecrets.write_text("google-client-secrets.json")

        ac = dfh.api.httpx.AsyncClient()
        with mock.patch.object(dfh.api.httpx, "AsyncClient") as m_client:
            m_client.return_value = ac

            # Minimum required environment variables.
            # NOTE: it is valid to not specify a Kubeconfig file, most notably when
            # running inside a Pod.
            new_env = {
                "DFH_MANAGED_BY": "foo",
                "DFH_ENV_LABEL": "bar",
            }
            with mock.patch.dict("os.environ", values=new_env, clear=True):
                cfg, err = dfh.api.compile_server_config()
                assert not err
                assert cfg == dfh.api.ServerConfig(
                    kubeconfig=Path(""),
                    kubecontext="",
                    managed_by="foo",
                    env_label="bar",
                    host="0.0.0.0",
                    port=5001,
                    loglevel="info",
                    httpclient=ac,
                )

            # Explicit values for everything.
            new_env = {
                "KUBECONFIG": "/tmp/kind-kubeconf.yaml",
                "KUBECONTEXT": "kind-kind",
                "DFH_MANAGED_BY": "foo",
                "DFH_ENV_LABEL": "bar",
                "DFH_LOGLEVEL": "error",
                "DFH_HOST": "1.2.3.4",
                "DFH_PORT": "1234",
            }
            with mock.patch.dict("os.environ", values=new_env, clear=True):
                cfg, err = dfh.api.compile_server_config()
                assert not err
                assert cfg == dfh.api.ServerConfig(
                    kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
                    kubecontext="kind-kind",
                    managed_by="foo",
                    env_label="bar",
                    host="1.2.3.4",
                    port=1234,
                    loglevel="error",
                    httpclient=ac,
                )

            # Must have correctly received the values from the `.env` file.
            cfg, err = dfh.api.compile_server_config()
            assert not err
            assert cfg == dfh.api.ServerConfig(
                kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
                kubecontext="kind-kind",
                managed_by="dfh",
                env_label="env",
                host="0.0.0.0",
                port=5001,
                loglevel="info",
                httpclient=ac,
            )

    def test_compile_server_config_err(self):
        # Invalid because DFH_MANAGED_BY and DFH_ENV_LABEL are both mandatory.
        with mock.patch.dict("os.environ", values={}, clear=True):
            _, err = dfh.api.compile_server_config()
            assert err

    @mock.patch.object(dfh.api, "fetch_secrets")
    def test_make_app(self, m_secrets):
        m_secrets.return_value = ("sess", "api", False)

        # Create app and verify it has all the salient attributes.
        app = dfh.api.make_app()
        extra = cast(dict, app.extra)  # type: ignore
        assert set(extra) == {
            "session-key",
            "api-token-key",
            "config",
            "db",
        }
        assert extra["api-token-key"] == "api"
        assert extra["session-key"] == "sess"

        # Expect hard abort if we could not get the secrets.
        m_secrets.return_value = ("", "", True)
        with pytest.raises(RuntimeError):
            dfh.api.make_app()


class TestBasicEndpoints:
    def test_get_root(self, client):
        # Must serve the webapp on all routes by default.
        for path in ("/", "/static/index.html", "/anywhere/but/api"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.text == "Placeholder static/index.html"

        # Assets are also used by static web apps.
        response = client.get("/demo/assets/index.html")
        assert response.status_code == 200
        assert response.text == "Placeholder assets/index.html"

    def test_get_healthz(self, client: TestClient):
        response = client.get("/healthz")
        assert response.status_code == 200
