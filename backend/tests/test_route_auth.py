import base64
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import google.oauth2.credentials
import httpx
import itsdangerous
import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from googleapiclient.errors import HttpError

import dfh
import dfh.api
import dfh.defaults
import dfh.generate
import dfh.k8s
import dfh.routers.auth as auth
import dfh.watch
from dfh.models import GoogleToken, UserMe, UserToken


@pytest.fixture
async def client():
    c = TestClient(dfh.api.make_app())
    c.base_url = c.base_url.join("/demo/api/auth")
    yield c


def get_session_cookie(response: httpx.Response) -> dict | None:
    """Return the decoded session cookie or `None` if it does not exist."""
    # Check that a session cookie is set in the response
    if "session" not in response.cookies:
        return None
    cookie = response.cookies["session"]

    session_key, _, err = dfh.api.fetch_secrets()
    assert not err

    # Use `itsdangerous` to decode the signed session cookie
    serializer = itsdangerous.TimestampSigner(session_key)
    unsigned_data = serializer.unsign(cookie)

    # Verify that the session data contains the expected value
    return json.loads(base64.b64decode(unsigned_data.decode("utf8")))


def create_session_cookie(data, valid: bool = True):
    """Return the signed session `data`.

    Use `valid=False` to deliberately use a mismatched secret. The server must
    detect the forgery and reject the request.

    """
    session_key, _, err = dfh.api.fetch_secrets()
    assert not err

    secret = session_key if valid else "some-invalid-secret"
    serializer = itsdangerous.TimestampSigner(secret)
    sess = serializer.sign(base64.b64encode(json.dumps(data).encode())).decode()
    return {"session": sess}


class TestGoogleAuthentication:
    def test_clear(self, client: TestClient):
        # Must return without error but do nothing.
        resp = client.get("/clear-session")
        assert resp.status_code == 200
        assert get_session_cookie(resp) is None

        # Create a fake session cookie.
        cookie = create_session_cookie({"credentials": {"foo": "bar"}})
        resp = client.get("/clear-session", cookies=cookie)
        assert resp.status_code == 200
        assert get_session_cookie(resp) is None

    def test_google_auth_bearer(self, client: TestClient):
        # Make Genuine Google API request with invalid token.
        data = GoogleToken(token="invalid-token").model_dump()
        resp = client.post("/validate-google-bearer-token", json=data)
        assert resp.status_code == 401
        assert get_session_cookie(resp) is None

        # Simulate a successful response from Google API.
        with mock.patch("httpx.AsyncClient.get", new=mock.AsyncMock()) as m_get:
            m_get.return_value = httpx.Response(200, json={"email": "foo@bar.com"})
            resp = client.post("/validate-google-bearer-token", json=data)
            assert resp.status_code == 200
            sess = get_session_cookie(resp)
            assert sess is not None and sess["email"] == "foo@bar.com"

            # NOTE: the cookie string is quoted because it contains @.
            # The browser will strip it out automatically. This is not a
            # problem for the `session` cookie since it is Base64 encoded under
            # the hood.
            assert resp.cookies["email"] == '"foo@bar.com"'


class TestAPIAuthentication:
    def test_get_token(self, client: TestClient):
        """GET /users/token fetch temporary API token."""
        url = "/users/token"

        # Must reject authentic session with missing email.
        cookies: dict = {"email": ""}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 401
        assert resp.json() == {"detail": "not logged in"}

        # Must reject authentic session with empty email.
        cookies: dict = {"email": ""}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 401
        assert resp.json() == {"detail": "not logged in"}

        # Must reject forged session.
        cookies: dict = {"email": "authenticated@user.com"}
        resp = client.get(url, cookies=create_session_cookie(cookies, valid=False))
        assert resp.status_code == 401

        # Must accept authentic session and return a token.
        cookies: dict = {"email": "authenticated@user.com"}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 200
        data = UserToken.model_validate(resp.json())
        assert data.token != ""

        # Unsign the token which is itself a UserToken model.
        _, api_key, err = dfh.api.fetch_secrets()
        assert not err

        unsigned = itsdangerous.TimestampSigner(api_key).unsign(data.token)
        info = UserToken.model_validate(json.loads(base64.b64decode(unsigned)))
        assert info.email == "authenticated@user.com"

        # Sanity check.
        with pytest.raises(itsdangerous.BadTimeSignature):
            itsdangerous.TimestampSigner("wrong-secret").unsign(data.token)

    def test_users_me(self, client: TestClient):
        """GET /users/me is a simple way to ensure authentication works."""
        # Must reject request without bearer token.
        assert client.get("/users/me").status_code == 401

        # Fake an authentic browser session to get an API token.
        cookies: dict = {"email": "authenticated@user.com"}
        resp = client.get("/users/token", cookies=create_session_cookie(cookies))
        assert resp.status_code == 200
        data = UserToken.model_validate(resp.json())
        headers = {"Authorization": f"Bearer {data.token}"}

        # Must reject request without bearer token.
        # NOTE: it is imperative to clear the session or otherwise we will
        # still be considered authenticated by the server since the TestClient
        # reuses existing sessions.
        assert client.get("/users/me", cookies={"session": ""}).status_code == 401

        # Must accept request with bearer token.
        resp = client.get("/users/me", headers=headers)
        assert resp.status_code == 200
        user = UserMe.model_validate(resp.json())
        assert user.email == "authenticated@user.com"

    def test_is_authenticated_rejected(self, client: TestClient):
        """Various scenarios where the `is_authenticated` dependency must deem
        the session as unauthenticated."""
        url = "/users/me"
        _, api_key, err = dfh.api.fetch_secrets()
        assert not err

        # No session or bearer token.
        assert client.get(url).status_code == 401

        # Use a valid bearer token.
        token = auth.mint_token("foo@bar.com", api_key).token
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get(url, headers=headers).status_code == 200

        # Various invalid bearer tokens.
        invalid_headers = [
            "",
            token,
            f" token ",
            f"bearer {token}",
            f"Bearer  {token}",
            f" Bearer {token}",
            f"Bearer {token} ",
            f"Bearer {token[:-1]} ",
        ]
        for value in invalid_headers:
            headers = {"Authorization": value}
            assert client.get(url, headers=headers).status_code == 401

    def test_is_authenticated_expired_token(self, client: TestClient):
        url = "/users/me"
        _, api_key, err = dfh.api.fetch_secrets()
        assert not err

        relative_time = datetime.now(timezone.utc) - timedelta(seconds=3595)
        with freeze_time(relative_time):
            token = auth.mint_token("foo@bar.com", api_key).token
            headers = {"Authorization": f"Bearer {token}"}
        assert client.get(url, headers=headers).status_code == 200

        relative_time = datetime.now(timezone.utc) - timedelta(seconds=3605)
        with freeze_time(relative_time):
            token = auth.mint_token("foo@bar.com", api_key).token
            headers = {"Authorization": f"Bearer {token}"}
        assert client.get(url, headers=headers).status_code == 401
