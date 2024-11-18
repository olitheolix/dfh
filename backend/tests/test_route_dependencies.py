from unittest import mock

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import GoogleAPIError

import dfh.routers.dependencies as deps
from dfh.models import UAMChild
from tests.test_route_uam import get_root_users

from .test_helpers import (
    create_root_client,
    flush_db,
    make_group,
    make_user,
    set_root_user,
)

ROOT_NAME = deps.ROOT_NAME


class TestDependencies:
    @pytest.fixture(autouse=True)
    def autoflush(self):
        flush_db()

    def test_create_spanner_client(self):
        new_env = {
            "DFH_SPANNER_DATABASE": "my-database",
            "DFH_SPANNER_INSTANCE": "my-instance",
            "DFH_GCP_PROJECT": "my-project",
        }
        with mock.patch.dict("os.environ", values=new_env):
            client, db, iid, err = deps.create_spanner_client()
            assert not err
            assert client is not None
            assert db is not None
            assert iid == "my-instance"

        with mock.patch.dict("os.environ", values={}, clear=True):
            assert deps.create_spanner_client() == (None, None, "", True)

    def test_can_login_direct_member(self):
        """All users in the `dfhlogin` group must be able to login."""
        _, db, _, err = deps.create_spanner_client()
        assert not err and db

        client = create_root_client("/demo/api/uam/v1")
        root_user = get_root_users()[0]

        invalid_emails = ["", "*", f"not-{root_user}"]
        for email in invalid_emails:
            with pytest.raises(HTTPException) as err:  # type: ignore
                deps.can_login(db, email)
                assert err.value.status_code == 401  # type: ignore
            del email

        # Owner of root group must always be able to login.
        deps.can_login(db, root_user)

        # Create the magic `dfhlogin` group.
        group, user = make_group(name="dfhlogin"), make_user(email="foo@bar.com")
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        # Normal user must still be unable to login because he is not a member of
        # `dfhlogin` yet.
        with pytest.raises(HTTPException) as err:
            deps.can_login(db, user.email)
        assert err.value.status_code == 401

        # Make the user a member of `dfhlogin`.
        resp = client.put(f"/groups/{group.name}/users", json=[user.email])
        assert resp.status_code == 201

        # User must now be allowed to login.
        assert deps.can_login(db, user.email) is None

    def test_can_login_indirect_member(self):
        """Inherited members of `dfhlogin` must not be able to login."""
        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        client = create_root_client("/demo/api/uam/v1")

        # Create the magic `dfhlogin` group.
        group1, group2 = make_group(name="dfhlogin"), make_group(name="other")
        user = make_user(email="foo@bar.com")
        assert client.post("/groups", json=group1.model_dump()).status_code == 201
        assert client.post("/groups", json=group2.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        loginchild = UAMChild(child="dfhlogin").model_dump()
        otherchild = UAMChild(child="other").model_dump()

        # Add user to the `other` group.
        resp = client.put("/groups/other/users", json=[user.email])
        assert resp.status_code == 201

        # Create root -> `dfhlogin` -> `other`.
        root_user = get_root_users()[0]
        client.put(f"/groups/{root_user}/children", json=loginchild).status_code
        client.put(f"/groups/dfhlogin/children", json=otherchild).status_code
        assert resp.status_code == 201

        # User must not be allowed to login because he is not a direct member
        # of `dfhlogin`.
        with pytest.raises(HTTPException) as err:
            deps.can_login(db, user.email)
        assert err.value.status_code == 401

    def test_can_login_disable_authorisation(self):
        """Special case: root owner is `*` means authorisation is disabled."""
        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        set_root_user("user@org.com")

        with pytest.raises(HTTPException) as err:
            deps.can_login(db, "foo@bar.com")
        assert err.value.status_code == 401

        set_root_user("*")
        deps.can_login(db, "foo@bar.com")

    def test_handle_spanner_exceptions(self):
        """Verify the Spanner wrapper intercepts the relevant errors.

        The possible errors here are not exhaustive but illustrative only. This
        will still produce full coverage since the logic is shared for all of
        them.

        """
        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        wrapper = deps.handle_spanner_exceptions

        @wrapper
        def unhandled_error():
            raise KeyError()

        with pytest.raises(HTTPException) as err:  # type: ignore
            unhandled_error()
        assert err.value.status_code == 500  # type: ignore

        @wrapper
        def generic_google_error():
            raise GoogleAPIError()

        with pytest.raises(HTTPException) as err:  # type: ignore
            generic_google_error()
        assert err.value.status_code == 500  # type: ignore

        @wrapper
        def not_found():
            with db.batch() as batch:
                batch.insert(table="invalid", columns=["foo"], values=[["foo"]])

        with pytest.raises(HTTPException) as err:  # type: ignore
            not_found()
        assert err.value.status_code == 404  # type: ignore

        @wrapper
        def failed_precondition():
            with db.batch() as batch:
                batch.insert(table="OrgGroups", columns=["email"], values=[[ROOT_NAME]])

        with pytest.raises(HTTPException) as err:  # type: ignore
            failed_precondition()
        assert err.value.status_code == 400  # type: ignore

        @wrapper
        def already_exists():
            with db.batch() as batch:
                batch.insert(
                    table="OrgGroups",
                    columns=["email", "owner", "provider", "description"],
                    values=[[ROOT_NAME, "owner", "provider", ""]],
                )

        with pytest.raises(HTTPException) as err:  # type: ignore
            already_exists()
        assert err.value.status_code == 409  # type: ignore

        @wrapper
        def http_error():
            raise HTTPException(200, detail="")

        with pytest.raises(HTTPException) as err:  # type: ignore
            http_error()
        assert err.value.status_code == 200  # type: ignore
