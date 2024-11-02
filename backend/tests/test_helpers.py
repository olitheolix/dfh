from fastapi.testclient import TestClient

import dfh.api

from .test_route_auth import create_session_cookie
from dfh.models import UAMUser
from faker import Faker

faker = Faker()


def create_authenticated_client(prefix: str) -> TestClient:
    # Create valid session cookies to pass authentication.
    cookies: dict = {"email": "authenticated@user.com"}
    cookies["email"] = "authenticated@user.com"

    client = TestClient(dfh.api.make_app(), cookies=create_session_cookie(cookies))
    client.base_url = client.base_url.join(prefix)
    return client


def make_user(
    email: str = "",
    name: str = "",
    lanid: str = "",
    slack: str = "",
) -> UAMUser:
    tmp_email = faker.unique.first_name().lower() + "@foo.com"
    return UAMUser(
        email=email if email else tmp_email,
        name=name if name else faker.unique.first_name(),
        lanid=lanid if lanid else faker.unique.first_name(),
        slack=slack if slack else faker.unique.first_name(),
    )
