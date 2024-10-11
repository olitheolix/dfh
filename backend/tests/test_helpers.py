import google.oauth2.credentials
from fastapi.testclient import TestClient

import dfh.api
import dfh.routers.auth as auth

from .test_route_auth import create_session_cookie


def create_authenticated_client(prefix: str) -> TestClient:
    # Create valid session cookies to pass authentication.
    creds = auth.credentials_to_dict(google.oauth2.credentials.Credentials(None))
    cookies: dict = {"credentials": creds, "email": "authenticated@user.com"}
    cookies["email"] = "authenticated@user.com"

    client = TestClient(dfh.api.make_app(), cookies=create_session_cookie(cookies))
    client.base_url = client.base_url.join(prefix)
    return client
