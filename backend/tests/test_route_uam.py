from typing import List
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from httpx import Response

import dfh.api
import dfh.routers.uam as uam
from dfh.models import UAMChild, UAMGroup, UAMUser

from .test_helpers import create_authenticated_client, make_group, make_user


@pytest.fixture
async def client():
    c = create_authenticated_client("/demo/api/uam/v1")
    assert c.delete("/test-flushdb").status_code == 200
    yield c


def get_groups(client: TestClient) -> List[UAMGroup]:
    """Return the parsed groups from the /groups endpoint."""
    resp = client.get("/groups")
    assert resp.status_code == 200
    out = [UAMGroup.model_validate(_) for _ in resp.json()]
    out.sort(key=lambda _: _.name)
    return out


def get_users(client: TestClient) -> List[UAMUser]:
    """Return the parsed groups from the /groups endpoint."""
    resp = client.get("/users")
    assert resp.status_code == 200
    out = [UAMUser.model_validate(_) for _ in resp.json()]
    out.sort(key=lambda _: _.name)
    return out


def add_users_to_group(
    client: TestClient, group: str, users: List[UAMUser]
) -> Response:
    emails = [_.email for _ in users]
    return client.post(f"/groups/{group}/users", json=emails)


def get_tree(client: TestClient) -> UAMGroup:
    """Return the tree root. This must always succeed."""
    resp = client.get("/tree")
    assert resp.status_code == 200
    return UAMGroup.model_validate(resp.json())


class TestFakeData:
    def test_create_and_delete_fake_dataset(self, client):
        """Merely verify that test-flushdb endpoint works."""
        # `client` fixture must have ensured that DB is empty.
        assert len(get_groups(client)) == 0
        assert len(get_users(client)) == 0
        root = get_tree(client)
        assert len(root.children) == len(root.users) == 0

        # Must not create dummy users and groups buy default.
        with mock.patch.object(dfh.api, "isLocalDev") as m_islocal:
            m_islocal.return_value = False
            uam.create_fake_uam_dataset()
            assert len(get_groups(client)) == 0
            assert len(get_users(client)) == 0

        # Create dummy users and groups.
        uam.create_fake_uam_dataset()

        # We must now have a non-zero amount of groups (and users).
        assert len(get_groups(client)) > 0
        assert len(get_users(client)) > 0
        root = get_tree(client)
        assert len(root.children) > 0 and len(root.users) == 0

        # Flush the DB and verify that all groups and users are gone again.
        assert client.delete("test-flushdb").status_code == 200

        assert len(get_groups(client)) == 0
        assert len(get_users(client)) == 0
        root = get_tree(client)
        assert len(root.children) == len(root.users) == 0


class TestUserAccessManagement:
    def test_add_unique_users(self, client: TestClient):
        # Sanity check: DB is empty.
        assert len(get_users(client)) == 0

        demo_users = [make_user() for _ in range(3)]
        demo_users.sort(key=lambda _: _.name)

        # Users must not yet exist.
        for user in demo_users:
            assert client.get(f"/users/{user.email}").status_code == 404

        # Add all users.
        for user in demo_users:
            assert client.post("/users", json=user.model_dump()).status_code == 201

        users = get_users(client)
        assert len(users) == 3 and users == demo_users

        # Query each user individually.
        for user in demo_users:
            resp = client.get(f"/users/{user.email}")
            assert resp.status_code == 200
            assert UAMUser.model_validate(resp.json()) == user

    def test_add_duplicate_users(self, client: TestClient):
        demo_users = sorted([make_user() for _ in range(3)], key=lambda _: _.name)

        # Add all users and verify.
        for user in demo_users:
            assert client.post("/users", json=user.model_dump()).status_code == 201
        users = get_users(client)
        assert len(users) == 3 and users == demo_users

        # Attempt to add an existing user a second time and verify it fails.
        assert client.post("/users", json=demo_users[0].model_dump()).status_code == 409

        # There must still only be the three original users.
        users = get_users(client)
        assert len(users) == 3 and users == demo_users

    def test_create_delete_groups(self, client: TestClient):
        groups = [
            make_group(name="bar"),
            make_group(name="foo"),
        ]

        # Add all groups and verify.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert get_groups(client) == groups

        # Silently ignore requests to delete a non-existing group.
        assert client.delete("/groups/does-not-exist").status_code == 204
        assert get_groups(client) == groups

        # Delete the `bar` group and verify that only `foo` is left.
        assert client.delete("/groups/bar").status_code == 204
        assert get_groups(client) == groups[1:]

    def test_groups_root(self, client: TestClient):
        """Must not allow to create or delete the root group."""
        root_name = uam.UAM_DB.root.name
        group = make_group(name=root_name)

        # Must not allow to create a group with the name as the root group.
        assert client.post("/groups", json=group.model_dump()).status_code == 422

        # Must not allow to delete root group.
        assert client.delete(f"/groups/{root_name}").status_code == 422

    def test_groups_duplicate(self, client: TestClient):
        groups = sorted([make_group() for _ in range(3)], key=lambda _: _.name)

        # Create demo groups.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert get_groups(client) == groups

        # Attempt to upload an existing group.
        resp = client.post("/groups", json=groups[0].model_dump())
        assert resp.status_code == 409
        assert get_groups(client) == groups

    def test_group_members(self, client: TestClient):
        group = make_group(name="foo")
        demo_users = [make_user() for _ in range(3)]

        # Must be unable to fetch group or add users to it.
        assert client.get("/groups/foo").status_code == 404
        resp = add_users_to_group(client, "foo", demo_users[:1])
        assert resp.status_code == 404

        # Create the group and verify that it has no members.
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        group = UAMGroup.model_validate(resp.json())
        assert len(group.users) == 0

        # Attempt to add a non-existing user to the group.
        resp = add_users_to_group(client, "foo", demo_users[:1])
        assert resp.status_code == 404

        # Create all users.
        for user in demo_users:
            assert client.post("/users", json=user.model_dump()).status_code == 201

        # Setting the users of a group must now work.
        resp = add_users_to_group(client, "foo", demo_users[:1])
        assert resp.status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        group = UAMGroup.model_validate(resp.json())
        assert group.users == {demo_users[0].email: demo_users[0]}

        # Setting multiple users must also work.
        resp = add_users_to_group(client, "foo", demo_users[1:])
        assert resp.status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        group = UAMGroup.model_validate(resp.json())
        assert group.users == {_.email: _ for _ in demo_users[1:]}

    def test_add_remove_children_basic(self, client: TestClient):
        """Add and remove child groups."""
        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
        ]

        # Create the groups.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201

        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        blahchild = UAMChild(child="blah").model_dump()

        # Must reject attempt to add an existing child to a non-existing group.
        assert client.post("/groups/blah/children", json=barchild).status_code == 404
        assert len(get_groups(client)) == 2

        # Must reject attempt to add a non-existing child to an existing group.
        assert client.post("/groups/foo/children", json=blahchild).status_code == 404
        assert len(get_groups(client)) == 2

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root_name = uam.UAM_DB.root.name
        assert (
            client.post(f"/groups/{root_name}/children", json=foochild).status_code
            == 201
        )
        assert client.post("/groups/foo/children", json=barchild).status_code == 201

        # Must reject attempt to delete an existing child of a non-existing group.
        assert client.delete("/groups/blah/children/bar").status_code == 404
        assert len(get_groups(client)) == 2

        # Must permit attempt to remove a non-existing child (just does nothing).
        assert client.delete("/groups/bar/children/blah").status_code == 204
        assert len(get_groups(client)) == 2

        # Must permit to remove `bar` from `foo`. Note: this must not delete
        # the group, merely unlink it.
        assert client.delete("/groups/foo/children/bar").status_code == 204
        assert len(get_groups(client)) == 2

        # Must permit to remove `foo` from root node.
        root_name = uam.UAM_DB.root.name
        assert client.delete(f"/groups/{root_name}/children/foo").status_code == 204
        assert len(get_groups(client)) == 2

    def test_add_remove_children(self, client: TestClient):
        """Add and remove child groups."""
        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
        ]

        # Create the groups.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201

        # Must reject to add children to a non-existing group.
        barchild = UAMChild(child="bar").model_dump()

        # Make `bar` a child of `foo`: foo -> bar
        # Operation must be idempotent.
        for _ in range(2):
            assert client.post("/groups/foo/children", json=barchild).status_code == 201
            groups = get_groups(client)
            foogroup = [_ for _ in groups if _.name == "foo"][0]
            bargroup = [_ for _ in groups if _.name == "bar"][0]
            assert set(foogroup.children.keys()) == {"bar"}
            assert set(bargroup.children.keys()) == set()

        # Remove `bar` as a child from `foo`
        for _ in range(2):
            assert client.delete("/groups/foo/children/bar").status_code == 204
            groups = get_groups(client)
            assert len(groups) == 2
            for group in groups:
                assert len(group.children) == 0

    def test_put_groups_err(self, client: TestClient):
        group = make_group(name="foo")

        # Must refuse to update a non-existing group.
        assert client.put("/groups", json=group.model_dump()).status_code == 404

        # Must refuse to update the root group.
        root = uam.UAM_DB.root
        assert client.put("/groups", json=root.model_dump()).status_code == 422

    def test_put_groups_ok(self, client: TestClient):
        group = make_group(name="foo")
        user = make_user()

        # Create a group and user.
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        # Update the group without any changes.
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1 and ret[0] == group

        # Change group attributes and update the record.
        group.owner += "foo"
        group.description += "foo"
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1 and ret[0] == group

        # Must ignore changes to the `children` field.
        group.owner += "bar"
        group.description += "bar"
        group.children["blah"] = make_group(name="blah")
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1
        assert ret[0].owner == group.owner
        assert ret[0].description == group.description
        assert ret[0].children == {}
        assert ret[0].users == {}

        # Must ignore changes to the `users` field.
        group.owner += "foobar"
        group.description += "foobar"
        group.children.clear()
        group.users[user.email] = user
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1
        assert ret[0].owner == group.owner
        assert ret[0].description == group.description
        assert ret[0].children == {}
        assert ret[0].users == {}

    def test_recursive_user_query(self, client: TestClient):
        """Create basic parent/child relationships *once*.

        The purpose of this test is to query all the users of a given group
        either in recursive mode (includes all users of all sub-groups) or just
        the group itself (non-recursive).

        """
        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
        ]
        demo_users = sorted([make_user() for _ in range(4)], key=lambda _: _.name)

        # Must reject to create children for non-existing groups.
        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        assert client.get("/groups/foo/users?recursive=0").status_code == 404
        assert client.post("/groups/foo/children", json=barchild).status_code == 404

        # Create the groups and users.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        for user in demo_users:
            assert client.post("/users", json=user.model_dump()).status_code == 201

        # Add two and three users to `foo` and `bar`, respectively. That is,
        # the second user now exists in both groups.
        assert add_users_to_group(client, "foo", demo_users[:2]).status_code == 201
        assert add_users_to_group(client, "bar", demo_users[1:]).status_code == 201

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = uam.UAM_DB.root.name
        assert client.post(f"/groups/{root}/children", json=foochild).status_code == 201
        assert client.post("/groups/foo/children", json=barchild).status_code == 201
        groups = get_groups(client)
        foogroup = [_ for _ in groups if _.name == "foo"][0]
        bargroup = [_ for _ in groups if _.name == "bar"][0]
        assert set(foogroup.children.keys()) == {"bar"}
        assert set(bargroup.children.keys()) == set()

        # Users `foo` and `bar` must report just their members.
        resp = client.get("/groups/foo/users?recursive=0")
        assert resp.status_code == 200
        foo_users = [UAMUser.model_validate(_) for _ in resp.json()]
        assert len(foo_users) == 2

        resp = client.get("/groups/bar/users?recursive=0")
        assert resp.status_code == 200
        bar_users = [UAMUser.model_validate(_) for _ in resp.json()]
        assert len(bar_users) == 3

        # In recursive mode, the members of `foo` must include the members of `bar`.
        resp = client.get("/groups/foo/users?recursive=1")
        assert resp.status_code == 200
        foo_users = [UAMUser.model_validate(_) for _ in resp.json()]
        assert len(foo_users) == 4

        resp = client.get("/groups/bar/users?recursive=1")
        assert resp.status_code == 200
        bar_users = [UAMUser.model_validate(_) for _ in resp.json()]
        assert len(bar_users) == 3

        # Query root node.
        root_name = uam.UAM_DB.root.name
        resp = client.get(f"/groups/{root_name}/users?recursive=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        resp = client.get(f"/groups/{root_name}/users?recursive=1")
        assert resp.status_code == 200
        bar_users = [UAMUser.model_validate(_) for _ in resp.json()]
        assert len(bar_users) == 4

    def test_reparents_cycles(self, client: TestClient):
        groups = [
            make_group(name="g1"),
            make_group(name="g2"),
            make_group(name="g3"),
            make_group(name="g4"),
        ]

        # Create the groups
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201

        # Must fail because a node cannot be its own child.
        reparent = UAMChild(child="g1").model_dump()
        assert client.post("/groups/g1/children", json=reparent).status_code == 409

        # Make `g2` a child of `g1` and `g4` and child of `g3`.
        # g1 -> g2
        # g3 -> g4
        reparent = UAMChild(child="g2").model_dump()
        assert client.post("/groups/g1/children", json=reparent).status_code == 201
        reparent = UAMChild(child="g4").model_dump()
        assert client.post("/groups/g3/children", json=reparent).status_code == 201

        # Must not allow g3 to become a child of g4.
        reparent = UAMChild(child="g3").model_dump()
        assert client.post("/groups/g4/children", json=reparent).status_code == 409

        # Put all 4 into a single chain g1 -> g2 -> g3 -> g4
        reparent = UAMChild(child="g3").model_dump()
        assert client.post("/groups/g2/children", json=reparent).status_code == 201

        # Must not allow to g1 to become a child of g4 since that would be cycle.
        reparent = UAMChild(child="g1").model_dump()
        assert client.post("/groups/g4/children", json=reparent).status_code == 409

    def test_tree(self, client: TestClient):
        # Root node must always exist and be empty initially.
        root = get_tree(client)
        assert root.provider == "none"
        assert root.owner == "none"
        assert len(root.users) == 0
        assert len(root.children) == 0

        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
        ]
        users = [make_user() for _ in range(2)]

        # Create the groups and users.
        for user in users:
            assert client.post("/users", json=user.model_dump()).status_code == 201
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert add_users_to_group(client, "foo", users[:1]).status_code == 201
        assert add_users_to_group(client, "bar", users[1:]).status_code == 201

        # Root node must still be empty because the groups have not been linked
        # into the org.
        root = get_tree(client)
        assert root.provider == "none"
        assert root.owner == "none"
        assert len(root.users) == 0
        assert len(root.children) == 0

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = uam.UAM_DB.root.name
        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        assert client.post(f"/groups/{root}/children", json=foochild).status_code == 201
        assert client.post("/groups/foo/children", json=barchild).status_code == 201

        # Root node must now contain the `foo` group but without any of its
        # users to save space when transmitting this to the client.
        root = get_tree(client)
        assert root.provider == "none"
        assert root.owner == "none"
        assert len(root.users) == 0
        assert set(root.children) == {"foo"}
        assert len(root.children["foo"].users) == 0

    def test_reparent_multiple_times(self, client: TestClient):
        demo_groups = [
            make_group(name="foo"),
            make_group(name="bar"),
            make_group(name="abc"),
        ]

        # Create the groups.
        for group in demo_groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201

        root = get_tree(client)
        assert len(root.children) == 0

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = uam.UAM_DB.root.name
        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        abcchild = UAMChild(child="abc").model_dump()
        assert client.post(f"/groups/{root}/children", json=abcchild).status_code == 201
        assert client.post(f"/groups/{root}/children", json=barchild).status_code == 201
        assert client.post(f"/groups/{root}/children", json=foochild).status_code == 201

        # Make `abc` a child of both `foo` and `bar`:
        # foo -> abc
        # bar -> abc
        assert client.post("/groups/foo/children", json=abcchild).status_code == 201
        assert client.post("/groups/bar/children", json=abcchild).status_code == 201
        root = get_tree(client)
        assert set(root.children) == {"foo", "bar", "abc"}
        assert root.children["foo"].children == {"abc": demo_groups[2]}
        assert root.children["bar"].children == {"abc": demo_groups[2]}
        assert len(root.children["abc"].children) == 0

        # Must allow chaining foo -> bar to form the hierarchy
        # foo:
        #   abc
        #   bar:
        #     abc
        barchild = UAMChild(child="bar").model_dump()
        assert client.post("/groups/foo/children", json=barchild).status_code == 201
        root = get_tree(client)
        assert set(root.children) == {"foo", "bar", "abc"}
        assert set(root.children["foo"].children) == {"abc", "bar"}
        assert len(root.children["abc"].children) == 0

    def test_remove_groups_and_users(self, client: TestClient):
        demo_groups = [
            make_group(name="foo"),
            make_group(name="bar"),
            make_group(name="abc"),
        ]
        demo_users = [
            make_user(email="foo@blah.com"),
            make_user(email="bar@blah.com"),
            make_user(email="abc@blah.com"),
        ]

        # Create groups and users.
        for group in demo_groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        for user in demo_users:
            assert client.post("/users", json=user.model_dump()).status_code == 201

        assert add_users_to_group(client, "foo", demo_users[:1]).status_code == 201
        assert add_users_to_group(client, "bar", demo_users[1:2]).status_code == 201
        assert add_users_to_group(client, "abc", demo_users[2:]).status_code == 201

        # Construct the following group layout.
        # root:
        #   foo:
        #     abc
        #     bar:
        #       abc
        abcchild = UAMChild(child="abc").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        foochild = UAMChild(child="foo").model_dump()
        assert (
            client.post(
                f"/groups/{uam.UAM_DB.root.name}/children", json=foochild
            ).status_code
            == 201
        )
        assert client.post("/groups/foo/children", json=abcchild).status_code == 201
        assert client.post("/groups/bar/children", json=abcchild).status_code == 201
        assert client.post("/groups/foo/children", json=barchild).status_code == 201

        groups = {_.name: _ for _ in get_groups(client)}
        assert len(groups) == 3
        assert set(groups["foo"].users) == {"foo@blah.com"}
        assert set(groups["bar"].users) == {"bar@blah.com"}
        assert set(groups["abc"].users) == {"abc@blah.com"}

        # Remove the `foo@blah.com` user.
        assert client.delete("/users/foo@blah.com").status_code == 204
        groups = {_.name: _ for _ in get_groups(client)}
        assert len(groups) == 3
        assert set(groups["foo"].users) == set()
        assert set(groups["bar"].users) == {"bar@blah.com"}
        assert set(groups["abc"].users) == {"abc@blah.com"}

        # Remove the `bar` group from the system. This must shrink the hierarchy:
        # root:
        #   foo:
        #     abc
        assert client.delete("/groups/bar").status_code == 204
        groups = {_.name: _ for _ in get_groups(client)}
        assert len(groups) == 2
        assert set(groups["foo"].users) == set()
        assert set(groups["abc"].users) == {"abc@blah.com"}

        # The `foo` group must only have `abc` as a child anymore.
        root = get_tree(client)
        assert set(root.children["foo"].children) == {"abc"}

        # The hierarchy starting at `foo` must only contain a single user
        # anymore because `foo` itself has none and the `bar` group was
        # removed, leaving only the user in the `abc` group.
        resp = client.get("/groups/foo/users?recursive=1")
        assert resp.status_code == 200
        foo_users = [UAMUser.model_validate(_) for _ in resp.json()]
        foo_users = {_.email for _ in foo_users}
        assert foo_users == {"abc@blah.com"}

        # Remove the `abc` group. After that, there must be no users left in `foo`.
        assert client.delete("/groups/abc").status_code == 204
        groups = {_.name: _ for _ in get_groups(client)}
        assert len(groups) == 1
        assert len(groups["foo"].users) == len(groups["foo"].children) == 0
        resp = client.get("/groups/foo/users?recursive=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        # Remove the `foo` group. The DB must not contain any groups anymore
        # but still have two users.
        assert client.delete("/groups/foo").status_code == 204
        assert len(get_groups(client)) == 0
        assert len(get_users(client)) == 2
