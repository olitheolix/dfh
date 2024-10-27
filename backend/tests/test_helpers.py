from fastapi.testclient import TestClient

import dfh.api

from .test_route_auth import create_session_cookie


def create_authenticated_client(prefix: str) -> TestClient:
    # Create valid session cookies to pass authentication.
    cookies: dict = {"email": "authenticated@user.com"}
    cookies["email"] = "authenticated@user.com"

    client = TestClient(dfh.api.make_app(), cookies=create_session_cookie(cookies))
    client.base_url = client.base_url.join(prefix)
    return client
