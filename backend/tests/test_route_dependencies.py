import pytest
from fastapi import HTTPException

import dfh.routers.dependencies as deps
from dfh.models import UAMChild
from dfh.routers.dependencies import can_login

from .test_helpers import (
    create_authenticated_client,
    flush_db,
    make_group,
    make_user,
)


class TestDependencies:
    def test_can_login_direct_member(self):
        """All users in the `dfhlogin` group must be able to login."""
        flush_db()
        client = create_authenticated_client("/demo/api/uam/v1")

        invalid_emails = ["", "*"]
        for email in invalid_emails:
            with pytest.raises(HTTPException) as err:
                can_login(email)
            assert err.value.status_code == 401
            del email

        # Root user must always be able to login.
        can_login(deps.UAM_DB.root.owner)

        # Create the magic `dfhlogin` group.
        group, user = make_group(name="dfhlogin"), make_user(email="foo@bar.com")
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        # Normal user must still be unable to login because he is not a member of
        # `dfhlogin` yet.
        with pytest.raises(HTTPException) as err:
            can_login(user.email)
        assert err.value.status_code == 401

        # Make the user a member of `dfhlogin`.
        resp = client.put(f"/groups/{group.name}/users", json=[user.email])
        assert resp.status_code == 201

        # User must still be unable to login because `dfhlogin` is not a direct
        # descendant of `root`.
        with pytest.raises(HTTPException) as err:
            can_login(user.email)
        assert err.value.status_code == 401

        # Parent `dfhlogin` to `root`.
        loginchild = UAMChild(child="dfhlogin").model_dump()
        root_name = deps.UAM_DB.root.name
        resp = client.put(f"/groups/{root_name}/children", json=loginchild)
        assert resp.status_code == 201

        # User must now be allowed to login.
        assert can_login(user.email) is None

    def test_can_login_indirect_member(self):
        """All members in child groups of `dfhlogin` must be able to login."""
        flush_db()
        client = create_authenticated_client("/demo/api/uam/v1")

        invalid_emails = ["", "*"]
        for email in invalid_emails:
            with pytest.raises(HTTPException) as err:
                can_login(email)
            assert err.value.status_code == 401
            del email

        # Root user must always be able to login.
        can_login(deps.UAM_DB.root.owner)

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

        # Parent `dfhlogin` to root.
        root_name = deps.UAM_DB.root.name
        client.put(f"/groups/{root_name}/children", json=loginchild).status_code

        # User must still be unable to login because his group is not a descendant
        # of `dfhlogin` yet.
        with pytest.raises(HTTPException) as err:
            can_login(user.email)
        assert err.value.status_code == 401

        # Parent `other` to `dfhlogin`.
        client.put(f"/groups/dfhlogin/children", json=otherchild).status_code
        assert resp.status_code == 201

        # User must now be allowed to login because he is now implicitly a part
        # of `dfhlogin` since he belongs to a group that has `dfhlogin` as a parent.
        assert can_login(user.email) is None

    def test_can_login_disable_authorisation(self):
        """Special case: root owner is `*` means authorisation is disabled."""
        flush_db()
        deps.UAM_DB.root.owner = "user@org.com"

        with pytest.raises(HTTPException) as err:
            can_login("foo@bar.com")
        assert err.value.status_code == 401

        deps.UAM_DB.root.owner = "*"
        can_login("foo@bar.com")
