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
    def test_schema_rewrite(self):
        fun = auth.rewrite_scheme
        urls = ["foo.com", "foo.com/", "foo.com/path"]

        with mock.patch.dict("os.environ", values={"LOCAL_DEV": "1"}, clear=True):
            assert dfh.api.isLocalDev()
            for url in urls:
                assert fun(f"http://{url}") == f"http://{url}"

            # Must not touch strings that do not start with http://
            assert fun("foo.bar") == "foo.bar"
            assert fun("foo.bar/http://") == "foo.bar/http://"
            assert fun("foo.bar/https://") == "foo.bar/https://"

        with mock.patch.dict("os.environ", values={}, clear=True):
            assert not dfh.api.isLocalDev()
            for url in urls:
                assert fun(f"http://{url}") == f"https://{url}"

            # Must not touch strings that do not start with https://
            assert fun("foo.bar") == "foo.bar"
            assert fun("foo.bar/http://") == "foo.bar/http://"
            assert fun("foo.bar/https://") == "foo.bar/https://"

    def test_authdemo(self, client: TestClient):
        assert client.get("/authdemo").status_code == 200

    @mock.patch.object(auth.google_auth_oauthlib.flow, "Flow")
    def test_login(self, m_flow, client: TestClient):
        """Basic test of login handler.

        There is little that we can tangibly test here since the implementation
        is boiler plate code from Google's SDK.

        """
        # Mock the Google flow calls.
        m_flow.from_client_secrets_file.return_value = m_flow
        m_flow.authorization_url.return_value = "http://redirect.com", "foo"

        # Login handler must redirect to some Google URLs which the Flow object
        # will produce at runtime.
        resp = client.get("/google-login", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "http://redirect.com"

        # Our handler must have added a `state` to the session.
        cookies = get_session_cookie(resp)
        assert cookies is not None and cookies["state"] == "foo"

    @mock.patch.object(auth.google_auth_oauthlib.flow, "Flow")
    @mock.patch.object(auth, "fetch_user_email")
    def test_oauth2callback(self, m_email, m_flow, client: TestClient):
        """Basic test of OAuth2Callback handler.

        There is little that we can tangibly test here since the implementation
        is boiler plate code from Google's SDK.

        """
        # Mock the Google flow attributes the handler needs.
        m_email.return_value = "foo@bar.com"
        m_flow.from_client_secrets_file.return_value = m_flow
        m_flow.credentials.token = "token"
        m_flow.credentials.refresh_token = "refresh-token"
        m_flow.credentials.token_uri = "token-uri"
        m_flow.credentials.client_id = "client-id"
        m_flow.credentials.client_secret = "client-secret"
        m_flow.credentials.scopes = "scopes"

        # Handler must redirect us to one of our own endpoints.
        resp = client.get(
            "/oauth2callback",
            cookies=create_session_cookie({"state": "foo"}),
            follow_redirects=False,
        )
        assert resp.status_code == 307
        expected_redirect = "http://testserver/demo/api/auth/test-google-api-request"
        assert resp.headers["location"] == expected_redirect

        # Callback must add the `email`, `credentials` and `state` entries.
        cookies = get_session_cookie(resp)
        assert cookies is not None
        assert set(cookies.keys()) == {"email", "credentials", "state"}

        # Validate the email and credentials.
        assert cookies["email"] == "foo@bar.com"
        assert cookies["credentials"] == auth.credentials_to_dict(m_flow.credentials)

    @mock.patch.object(auth.google.oauth2.credentials, "Credentials")
    @mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock)
    def test_revoke(self, m_requests, m_oauth2, client: TestClient):
        # Must return HTML page if we are not authenticated.
        resp = client.get("/revoke")
        assert resp.status_code == 200
        assert resp.read().decode().startswith("You need to")

        # Create a fake session cookie.
        cookie = create_session_cookie({"credentials": {"foo": "bar"}})
        m_oauth2.return_value = m_oauth2
        m_oauth2.token = "token"

        m_requests.return_value = httpx.Response(200)
        resp = client.get("/revoke", cookies=cookie)
        assert resp.status_code == 200
        assert resp.read().decode() == '"Credentials successfully revoked."'

        m_requests.return_value = httpx.Response(403)
        resp = client.get("/revoke", cookies=cookie)
        assert resp.status_code == 200
        assert resp.read().decode() == '"Could not revoke credentials."'

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
        assert resp.status_code == 403
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

    @mock.patch.object(auth.googleapiclient.discovery, "build")
    def test_fetch_user_email(self, m_build):
        m_build.return_value = m_build
        m_build.userinfo.return_value = m_build
        m_build.get.return_value = m_build
        m_build.execute.return_value = {"email": "foo@bar.com"}

        creds = google.oauth2.credentials.Credentials(None)
        assert auth.fetch_user_email(creds) == "foo@bar.com"

        error_content = json.dumps(
            {
                "error": {
                    "code": 403,
                    "message": "Forbidden",
                    "errors": [{"message": "Forbidden", "reason": "forbidden"}],
                }
            }
        ).encode("utf-8")

        err = HttpError(resp=mock.MagicMock(status=403), content=error_content)
        m_build.execute.side_effect = err
        assert auth.fetch_user_email(creds) == ""

    @mock.patch.object(auth, "fetch_user_email")
    def test_google_api_request(self, m_email, client: TestClient):
        url = "/test-google-api-request"
        m_email.return_value = "foo@bar.com"
        creds = auth.credentials_to_dict(google.oauth2.credentials.Credentials(None))
        cookies: dict = {"credentials": creds, "email": ""}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 403
        assert resp.json() == {"detail": "not logged in"}

        cookies["email"] = "authenticated@user.com"
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 200
        assert resp.read() == b"User: foo@bar.com"


class TestAPIAuthentication:
    def test_get_token(self, client: TestClient):
        """GET /users/token fetch temporary API token."""
        url = "/users/token"

        # Must reject authentic session with missing email.
        cookies: dict = {"email": ""}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 403
        assert resp.json() == {"detail": "not logged in"}

        # Must reject authentic session with empty email.
        cookies: dict = {"email": ""}
        resp = client.get(url, cookies=create_session_cookie(cookies))
        assert resp.status_code == 403
        assert resp.json() == {"detail": "not logged in"}

        # Must reject forged session.
        cookies: dict = {"email": "authenticated@user.com"}
        resp = client.get(url, cookies=create_session_cookie(cookies, valid=False))
        assert resp.status_code == 403

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
        # Fake an authentic browser session to get an API token.
        cookies: dict = {"email": "authenticated@user.com"}
        resp = client.get("/users/token", cookies=create_session_cookie(cookies))
        assert resp.status_code == 200
        data = UserToken.model_validate(resp.json())
        headers = {"Authorization": f"Bearer {data.token}"}

        # Must reject request without bearer token.
        assert client.get("/users/me").status_code == 403

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
        assert client.get(url).status_code == 403

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
            assert client.get(url, headers=headers).status_code == 403

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
        assert client.get(url, headers=headers).status_code == 403
