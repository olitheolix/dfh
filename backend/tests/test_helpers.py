import httpx
import itsdangerous
import base64
import random
import json

from faker import Faker
from fastapi.testclient import TestClient

import dfh.api
import dfh.routers.uam as uam
from dfh.models import UAMGroup, UAMUser


faker = Faker()


def flush_db():
    uam.UAM_DB.users.clear()
    uam.UAM_DB.groups.clear()
    uam.UAM_DB.root = UAMGroup(name="Org", owner="none", provider="none")


def create_authenticated_client(prefix: str) -> TestClient:
    # Create a random root user.
    name, org = faker.unique.first_name(), faker.unique.first_name()
    uam.UAM_DB.root.owner = f"{name}@{org}.com"

    # Create valid session cookies to indicate we are the root user.
    cookies: dict = {"email": uam.UAM_DB.root.owner}

    client = TestClient(dfh.api.make_app(), cookies=create_session_cookie(cookies))
    client.base_url = client.base_url.join(prefix)
    return client


def make_user(
    email: str = "",
    name: str = "",
    lanid: str = "",
    slack: str = "",
    role: str = "",
    manager: str = "",
) -> UAMUser:
    tmp_email = faker.unique.first_name().lower() + "@foo.com"
    return UAMUser(
        email=email if email else tmp_email,
        name=name if name else faker.unique.first_name(),
        lanid=lanid if lanid else faker.unique.first_name(),
        slack=slack if slack else faker.unique.first_name(),
        role=role if role else faker.unique.first_name(),
        manager=manager if manager else faker.unique.first_name(),
    )


def make_group(
    name: str = "",
    owner: str = "",
    provider: str = "",
) -> UAMGroup:
    return UAMGroup(
        name=name if name else faker.unique.first_name(),
        owner=owner if owner else faker.unique.first_name(),
        provider=provider if provider else random.choice(["google", "github"]),
    )


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
