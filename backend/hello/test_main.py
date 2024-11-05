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
        assert response.text == "hello world"

    def test_get_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200

    @pytest.mark.parametrize("prefix", ["", "/foo", "/foo/bar/blah"])
    def test_get_envvar(self, prefix, client):
        # Sanity check: prefixes must not contain a trailing slash or it will
        # produce invalid paths in our test.
        assert not prefix.endswith("/")

        with mock.patch.dict("os.environ", values={"FOO": "bar"}, clear=True):
            response = client.get(f"{prefix}/envvar/foo")
            assert response.status_code == 200
            assert response.text == "Environment Variable: foo=<undefined>\n"

            response = client.get(f"{prefix}/envvar/FOO")
            assert response.status_code == 200
            assert response.text == "Environment Variable: FOO=bar\n"
