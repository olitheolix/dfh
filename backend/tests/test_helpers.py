import base64
import json
import random

import httpx
import itsdangerous
from faker import Faker
from fastapi.testclient import TestClient
from google.cloud import spanner

import dfh.api
import dfh.routers.dependencies as deps
import dfh.routers.uam as uam
from dfh.models import UAMGroup, UAMUser

faker = Faker()


def set_root_group(
    owner: str,
    provider: str = "provider",
    description: str = "description",
):
    # fixme: docu
    _, db, _, err = deps.create_spanner_client()
    assert not err and db
    with db.batch() as batch:
        batch.insert_or_update(
            table="OrgGroups",
            columns=["email", "owner", "provider", "description"],
            values=[("Org", owner, provider, description)],
        )


def get_root_group() -> UAMGroup:
    _, db, _, err = deps.create_spanner_client()
    assert not err and db
    return uam.spanner_get_group(db, "Org")


def flush_db():
    _, db, _, err = deps.create_spanner_client()
    assert not err and db
    with db.batch() as batch:
        batch.delete("OrgUsers", spanner.KeySet(all_=True))
        batch.delete("OrgGroups", spanner.KeySet(all_=True))
        batch.delete("OrgGroupsUsers", spanner.KeySet(all_=True))
        batch.delete("OrgGroupsGroups", spanner.KeySet(all_=True))
        batch.delete("OrgGroupsRoles", spanner.KeySet(all_=True))

    # Create a random owner of the root group to ensure we have no hard coded
    # names anywhere.
    name, org = faker.unique.first_name(), faker.unique.first_name()
    owner = f"{name}@{org}.com"
    set_root_group(owner)


def create_root_client(prefix: str, owner: str | None = None) -> TestClient:
    if not owner:
        owner = get_root_group().owner

    # Create valid session cookies to indicate we are the root user.
    cookies: dict = {"email": owner}

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
