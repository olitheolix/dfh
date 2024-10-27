from unittest import mock

import pytest
from fastapi.testclient import TestClient

import hello.main


@pytest.fixture
def client():
    with TestClient(hello.main.app) as tc:
        yield tc


class TestHello:
    def test_get_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"Hello": "World"}

    def test_get_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200

    def test_get_envvar(self, client):
        with mock.patch.dict("os.environ", values={"FOO": "bar"}, clear=True):
            response = client.get("/envvar/foo")
            assert response.status_code == 200
            assert response.text == "Environment Variable: foo=<undefined>\n"

            response = client.get("/envvar/FOO")
            assert response.status_code == 200
            assert response.text == "Environment Variable: FOO=bar\n"
