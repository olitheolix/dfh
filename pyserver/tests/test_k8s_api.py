from pathlib import Path
from unittest import mock

import httpx
import pytest
import respx
import yaml
from httpx import Response
from tenacity import wait_none

import dfh.k8s
from dfh.models import PodList

from .conftest import K8sConfig


@pytest.mark.parametrize("status", [200, 403])
@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
class TestRequestCommon:
    async def test_basic(self, method, status, k8scfg: K8sConfig):
        """Basic test to run through all methods once."""
        path, payload = "/api/crt/v1/namespaces", {"foo": "bar"}

        # Mock the HTTP response.
        m_http = getattr(respx, method)(path)  # eg `respx.get(path)`
        m_http.return_value = Response(status, json=payload)

        # Function must return the expected payload.
        ret, status_code, err = await dfh.k8s.request(k8scfg, method, path)
        assert not err
        assert status_code == status
        assert ret == payload

    async def test_corrupt_json_payload(self, method, status, k8scfg: K8sConfig):
        """Gracefully handle JSON decoding errors."""
        path = "/api/crt/v1/namespaces"

        # Setup mock response.
        m_http = getattr(respx, method)(path)  # eg `respx.get(path)`
        m_http.return_value = Response(
            status, text="{invalid json]", headers={"content-type": "application/json"}
        )

        # Function must gracefully handle corrupt JSON response.
        _, _, err = await dfh.k8s.request(k8scfg, method, path)
        assert err

    async def test_handled_exceptions(self, method, status, k8scfg: K8sConfig):
        """`k8s.request` must intercept standard network and async exceptions."""
        path = "/api/crt/v1/namespaces"
        assert status  # Stop linter from flagging unused fixture.

        # Disable Tenacity's sleep function.
        dfh.k8s._call.retry.wait = wait_none()  # type: ignore

        # Setup mock response.
        m_http = getattr(respx, method)(path)  # eg `respx.get(path)`
        m_http.side_effect = httpx.ReadTimeout

        # Verify that the function handles intercepts the exceptions.
        _, _, err = await dfh.k8s.request(k8scfg, method, path)
        assert err


class TestRequestHelpers:
    @pytest.mark.parametrize("err", [True, False])
    async def test_api_methods(self, err: bool, k8scfg: K8sConfig):
        path = "/some/path"

        with mock.patch.object(dfh.k8s, "request") as m_req:
            m_req.return_value = ({"foo": "bar"}, 200, err)
            resp = await dfh.k8s.get(k8scfg, path)
        assert resp == ({"foo": "bar"}, err)
        m_req.assert_called_once_with(k8scfg, "GET", path, payload=None, headers=None)

        with mock.patch.object(dfh.k8s, "request") as m_req:
            m_req.return_value = ({"foo": "bar"}, 201, err)
            resp = await dfh.k8s.post(k8scfg, path, {"post": "payload"})
        assert resp == ({"foo": "bar"}, err)
        m_req.assert_called_once_with(
            k8scfg, "POST", path, {"post": "payload"}, headers=None
        )

        with mock.patch.object(dfh.k8s, "request") as m_req:
            m_req.return_value = ({"foo": "bar"}, 200, err)
            resp = await dfh.k8s.patch(k8scfg, path, [{"foo": "bar"}])
        assert resp == ({"foo": "bar"}, err)
        m_req.assert_called_once_with(
            k8scfg,
            "PATCH",
            path,
            [{"foo": "bar"}],
            {"Content-Type": "application/json-patch+json"},
        )

        with mock.patch.object(dfh.k8s, "request") as m_req:
            m_req.return_value = ({"foo": "bar"}, 200, err)
            resp = await dfh.k8s.delete(k8scfg, path, {"delete": "payload"})
        assert resp == ({"foo": "bar"}, err)
        m_req.assert_called_once_with(
            k8scfg,
            "DELETE",
            path,
            {"delete": "payload"},
            headers=None,
        )


class TestK8sUtilities:
    def test_parse_pod_info_scheduled_and_running(self):
        manifest = yaml.safe_load(Path("tests/support/pod-running.yaml").read_text())
        manifest["metadata"]["name"] = "demo"
        manifest["metadata"]["namespace"] = "default"

        info, err = dfh.k8s.parse_pod_info(manifest)
        assert not err

        assert info.id == "default/demo"
        assert info.name == "demo"
        assert info.namespace == "default"
        assert info.phase == "Running"
        assert info.ready == "2/2"
        assert info.restarts == 0
        assert info.age != ""
        assert info.reason == ""
        assert info.message == ""

    def test_parse_pod_info_scheduled_and_imagepullbackoff(self):
        manifest = yaml.safe_load(Path("tests/support/pod-backoff.yaml").read_text())
        manifest["metadata"]["name"] = "demo"
        manifest["metadata"]["namespace"] = "default"

        info, err = dfh.k8s.parse_pod_info(manifest)
        assert not err

        assert info.id == "default/demo"
        assert info.name == "demo"
        assert info.namespace == "default"
        assert info.phase == "Pending"
        assert info.ready == "1/2"
        assert info.restarts == 0
        assert info.age != ""
        assert info.reason == "nginx: ImagePullBackOff"
        assert info.message.startswith("nginx: Back-off pulling image")

    def test_parse_pod_info_unschedulable(self):
        manifest = yaml.safe_load(
            Path("tests/support/pod-unschedulable.yaml").read_text()
        )
        manifest["metadata"]["name"] = "demo"
        manifest["metadata"]["namespace"] = "default"

        info, err = dfh.k8s.parse_pod_info(manifest)
        assert not err

        assert info.id == "default/demo"
        assert info.name == "demo"
        assert info.namespace == "default"
        assert info.phase == "Pending"
        assert info.ready == "0/2"
        assert info.restarts == 0
        assert info.age != ""
        assert info.reason == "Unschedulable"
        assert info.message.startswith("0/1 nodes are available")

    def test_parse_pod_info_invalid(self):
        _, err = dfh.k8s.parse_pod_info({})
        assert err
