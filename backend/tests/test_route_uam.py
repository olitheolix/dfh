from typing import Dict, List

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.cloud import spanner
from httpx import Response

import dfh.routers.dependencies as deps
import dfh.routers.uam as uam
from dfh.models import (
    UAMChild,
    UAMGroup,
    UAMRoles,
    UAMTreeInfo,
    UAMUser,
    UAMUserRoles,
)

from .test_helpers import (
    create_root_client,
    flush_db,
    get_root_group,
    make_group,
    make_user,
    set_root_group,
)


@pytest.fixture
async def client():
    flush_db()
    yield create_root_client("/demo/api/uam/v1")


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
    return client.put(f"/groups/{group}/users", json=emails)


def get_tree(client: TestClient) -> UAMTreeInfo:
    """Return the tree root. This must always succeed."""
    resp = client.get("/tree")
    assert resp.status_code == 200
    return UAMTreeInfo.model_validate(resp.json())


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
        group = make_group(name="Org")
        c_user = create_root_client("/demo/api/uam/v1", "user-1@org.com")

        # Not even root must be allowed to create a group with the same name as the root group.
        assert client.post("/groups", json=group.model_dump()).status_code == 422
        assert c_user.post("/groups", json=group.model_dump()).status_code == 422

        # Not even root can delete the `Org` group.
        assert client.delete(f"/groups/Org").status_code == 422
        assert c_user.delete(f"/groups/Org").status_code == 422

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
        assert group.users == [demo_users[0].email]

        # Setting multiple users must also work.
        resp = add_users_to_group(client, "foo", demo_users[1:])
        assert resp.status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        group = UAMGroup.model_validate(resp.json())
        assert set(group.users) == {_.email for _ in demo_users[1:]}

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
        assert client.put("/groups/blah/children", json=barchild).status_code == 404
        assert len(get_groups(client)) == 2

        # Must reject attempt to add a non-existing child to an existing group.
        assert client.put("/groups/foo/children", json=blahchild).status_code == 404
        assert len(get_groups(client)) == 2

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = get_root_group()
        assert (
            client.put(f"/groups/{root.name}/children", json=foochild).status_code
            == 201
        )
        assert client.put("/groups/foo/children", json=barchild).status_code == 201

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
        assert client.delete(f"/groups/{root.name}/children/foo").status_code == 204
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
            assert client.put("/groups/foo/children", json=barchild).status_code == 201
            groups = get_groups(client)
            foogroup = [_ for _ in groups if _.name == "foo"][0]
            bargroup = [_ for _ in groups if _.name == "bar"][0]
            assert set(foogroup.children) == {"bar"}
            assert set(bargroup.children) == set()

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
        root = get_root_group()
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
        group.children.append("blah")
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1
        assert ret[0].owner == group.owner
        assert ret[0].description == group.description
        assert len(ret[0].children) == 0
        assert len(ret[0].users) == 0

        # Must ignore changes to the `users` field.
        group.owner += "foobar"
        group.description += "foobar"
        group.children.clear()
        group.users.append(user.email)
        assert client.put("/groups", json=group.model_dump()).status_code == 204
        ret = get_groups(client)
        assert len(ret) == 1
        assert ret[0].owner == group.owner
        assert ret[0].description == group.description
        assert len(ret[0].children) == 0
        assert len(ret[0].users) == 0

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
        assert client.put("/groups/foo/children", json=barchild).status_code == 404

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
        root = get_root_group()
        assert (
            client.put(f"/groups/{root.name}/children", json=foochild).status_code
            == 201
        )
        assert client.put("/groups/foo/children", json=barchild).status_code == 201
        groups = get_groups(client)
        foogroup = [_ for _ in groups if _.name == "foo"][0]
        bargroup = [_ for _ in groups if _.name == "bar"][0]
        assert set(foogroup.children) == {"bar"}
        assert set(bargroup.children) == set()

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
        resp = client.get(f"/groups/{root.name}/users?recursive=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        resp = client.get(f"/groups/{root.name}/users?recursive=1")
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
        assert client.put("/groups/g1/children", json=reparent).status_code == 409

        # Make `g2` a child of `g1` and `g4` and child of `g3`.
        # g1 -> g2
        # g3 -> g4
        reparent = UAMChild(child="g2").model_dump()
        assert client.put("/groups/g1/children", json=reparent).status_code == 201
        reparent = UAMChild(child="g4").model_dump()
        assert client.put("/groups/g3/children", json=reparent).status_code == 201

        # Must not allow g3 to become a child of g4.
        reparent = UAMChild(child="g3").model_dump()
        assert client.put("/groups/g4/children", json=reparent).status_code == 409

        # Put all 4 into a single chain g1 -> g2 -> g3 -> g4
        reparent = UAMChild(child="g3").model_dump()
        assert client.put("/groups/g2/children", json=reparent).status_code == 201

        # Must not allow to g1 to become a child of g4 since that would be cycle.
        reparent = UAMChild(child="g1").model_dump()
        assert client.put("/groups/g4/children", json=reparent).status_code == 409

    def test_tree(self, client: TestClient):
        # Root node must always exist and be empty initially.
        tree = get_tree(client)
        assert len(tree.root.children) == 0
        assert set(tree.groups) == {"Org"}

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
        # into the org. Consequently, the list of groups in the tree (which may
        # be fewer than there are groups in the system) is still 1.
        tree = get_tree(client)
        assert len(tree.root.children) == 0
        assert set(tree.groups) == {"Org"}

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = get_root_group()
        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        assert (
            client.put(f"/groups/{root.name}/children", json=foochild).status_code
            == 201
        )
        assert client.put("/groups/foo/children", json=barchild).status_code == 201

        # Root node must now contain the `foo` group but without any of its
        # users to save space when transmitting this to the client.
        tree = get_tree(client)
        assert set(tree.root.children) == {"foo"}
        assert set(tree.groups) == {"Org", "foo", "bar"}

    def test_reparent_multiple_times(self, client: TestClient):
        demo_groups = [
            make_group(name="foo"),
            make_group(name="bar"),
            make_group(name="abc"),
        ]

        # Create the groups.
        for group in demo_groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201

        tree = get_tree(client)
        assert len(tree.root.children) == 0
        assert set(tree.groups) == {"Org"}

        # Create root -> `foo` -> `bar` for basic deletion tests.
        root = get_root_group()
        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        abcchild = UAMChild(child="abc").model_dump()
        url = f"/groups/{root.name}/children"
        assert client.put(url, json=abcchild).status_code == 201
        assert client.put(url, json=barchild).status_code == 201
        assert client.put(url, json=foochild).status_code == 201

        # Make `abc` a child of both `foo` and `bar`:
        # foo -> abc
        # bar -> abc
        assert client.put("/groups/foo/children", json=abcchild).status_code == 201
        assert client.put("/groups/bar/children", json=abcchild).status_code == 201
        tree = get_tree(client)
        assert set(tree.root.children) == {"foo", "bar", "abc"}
        assert set(tree.groups) == {"Org", "foo", "bar", "abc"}
        assert set(tree.groups["foo"].children) == {"abc"}
        assert set(tree.groups["bar"].children) == {"abc"}
        assert len(tree.root.children["abc"].children) == 0

        # Must allow chaining foo -> bar to form the hierarchy
        # foo:
        #   abc
        #   bar:
        #     abc
        barchild = UAMChild(child="bar").model_dump()
        assert client.put("/groups/foo/children", json=barchild).status_code == 201
        tree = get_tree(client)
        assert set(tree.root.children) == {"foo", "bar", "abc"}
        assert set(tree.groups) == {"Org", "foo", "bar", "abc"}
        assert set(tree.root.children["foo"].children) == {"abc", "bar"}
        assert len(tree.root.children["abc"].children) == 0

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
        root = get_root_group()
        assert (
            client.put(f"/groups/{root.name}/children", json=foochild).status_code
            == 201
        )
        assert client.put("/groups/foo/children", json=abcchild).status_code == 201
        assert client.put("/groups/bar/children", json=abcchild).status_code == 201
        assert client.put("/groups/foo/children", json=barchild).status_code == 201

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
        tree = get_tree(client)
        assert set(tree.root.children["foo"].children) == {"abc"}

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


class TestUsers:
    def test_get_put_user_roles_err(self, client: TestClient):
        # Must return 404 if we try to fetch permissions of an unknown user.
        resp = client.get("/users/does-not-exist/roles")
        assert resp.status_code == 404

        # Must return 404 if we try to set permissions of an unknown group.
        roles: UAMRoles = ["role-1", "role-2"]
        resp = client.put("/groups/does-not-exist/roles", json=roles)
        assert resp.status_code == 404

    def test_set_group_roles_basic(self, client: TestClient):
        # Fixtures.
        group = make_group(name="foo")

        # Create the group and verify it has no roles by default.
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        assert UAMGroup.model_validate(resp.json()).roles == []

        # Set new roles and verify.
        roles = ["role-1"]
        assert client.put("/groups/foo/roles", json=roles).status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        assert UAMGroup.model_validate(resp.json()).roles == roles

        # Replace the roles with new ones.
        roles = ["role-2", "role-3"]
        assert client.put("/groups/foo/roles", json=roles).status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        assert UAMGroup.model_validate(resp.json()).roles == roles

        # Must remove duplicates.
        roles = ["role-4", "role-4"]
        assert client.put("/groups/foo/roles", json=roles).status_code == 201
        resp = client.get("/groups/foo")
        assert resp.status_code == 200
        assert UAMGroup.model_validate(resp.json()).roles == ["role-4"]

    def test_put_group_members_bug(self, client: TestClient):
        """Must not break if the list of members to update is empty."""
        # Fixtures.
        group = make_group(name="foo")

        # Create the group.
        assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.put("/groups/foo/users", json=[]).status_code == 201

    def test_get_user_roles(self, client: TestClient):
        # Fixtures.
        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
        ]
        user = make_user()

        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()

        url_0 = f"/groups/{groups[0].name}/roles"
        url_1 = f"/groups/{groups[1].name}/roles"
        roles_0 = ["role-1", "role-2"]
        roles_1 = ["role-1", "role-3"]

        # Create the groups and user.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        def get_perms() -> Dict[str, List[str]]:
            """Helper function to return the roles of the user."""
            resp = client.get(f"/users/{user.email}/roles")
            assert resp.status_code == 200
            data = UAMUserRoles.model_validate(resp.json())
            perms = {k: list(sorted(v)) for k, v in data.inherited.items()}
            return perms

        # User must not have inherited any roles because he is not a member of
        # any group yet.
        assert get_perms() == {}

        # Assign group roles and verify the user still has no inherited roles
        # because he is still not a member of any group.
        assert client.put(url_0, json=roles_0).status_code == 201
        assert client.put(url_1, json=roles_1).status_code == 201
        assert get_perms() == {}

        # Create hierarchy: Org -> foo -> bar
        # User must still not have any inherited roles because he is still not a
        # member of any group.
        root = get_root_group()
        resp = client.put(f"/groups/{root.name}/children", json=foochild)
        assert resp.status_code == 201
        resp = client.put(f"/groups/{groups[0].name}/children", json=barchild)
        assert resp.status_code == 201
        assert get_perms() == {}

        # Make user a member of the bar group and verify that he inherited all
        # the roles from both groups.
        assert client.put("/groups/bar/users", json=[user.email]).status_code == 201
        assert get_perms() == {
            "role-1": ["bar", "foo"],
            "role-2": ["foo"],
            "role-3": ["bar"],
        }

        # Remove all roles from the `foo` group. Use must now only have
        # the roles of the `bar` group.
        assert client.put(url_0, json=[]).status_code == 201
        assert get_perms() == {"role-1": ["bar"], "role-3": ["bar"]}

        # Remove all roles from the `bar` group and verify that the user
        # has no inherited roles anymore since none of its parents does.
        assert client.put(url_1, json=[]).status_code == 201
        assert get_perms() == {}

        # Add roles to `bar` group and verify the user inherits it.
        assert client.put(url_0, json=roles_0).status_code == 201
        assert get_perms() == {"role-1": ["foo"], "role-2": ["foo"]}

    def test_get_user_roles_bug(self, client: TestClient):
        """Recreate the scenario that surfaced a bug in the tree traversal."""
        # Fixtures.
        groups = [
            make_group(name="foo"),
            make_group(name="bar"),
            make_group(name="xyz"),
        ]
        user = make_user()

        foochild = UAMChild(child="foo").model_dump()
        barchild = UAMChild(child="bar").model_dump()
        xyzchild = UAMChild(child="xyz").model_dump()

        # Create the groups and user.
        for group in groups:
            assert client.post("/groups", json=group.model_dump()).status_code == 201
        assert client.post("/users", json=user.model_dump()).status_code == 201

        def get_perms() -> Dict[str, List[str]]:
            """Helper function to return the roles of the user."""
            resp = client.get(f"/users/{user.email}/roles")
            assert resp.status_code == 200
            data = UAMUserRoles.model_validate(resp.json())
            perms = {k: list(sorted(v)) for k, v in data.inherited.items()}
            return perms

        # User must not have any inherited any roles because he is not a member
        # of any group yet.
        assert get_perms() == {}

        # Create hierarchy:
        # org
        #   foo
        #     xyz
        #   bar
        root = get_root_group()
        resp = client.put(f"/groups/{root.name}/children", json=foochild)
        assert resp.status_code == 201
        resp = client.put(f"/groups/{root.name}/children", json=barchild)
        assert resp.status_code == 201
        resp = client.put(f"/groups/foo/children", json=xyzchild)
        assert resp.status_code == 201

        assert get_perms() == {}

        assert client.put(f"/groups/foo/roles", json=["role-foo"]).status_code == 201
        assert client.put(f"/groups/bar/roles", json=["role-bar"]).status_code == 201
        assert client.put(f"/groups/xyz/roles", json=["role-xyz"]).status_code == 201

        # Make user a member of the `bar` group. User must now have inherited
        # the roles of `bar` but nothing else.
        assert client.put("/groups/bar/users", json=[user.email]).status_code == 201
        assert get_perms() == {
            "role-bar": ["bar"],
        }


class TestRBAC:
    @pytest.fixture(autouse=True)
    def autoflush(self):
        flush_db()

    @pytest.mark.parametrize("org_edit", [True, False])
    def test_can_edit_existing_group(self, org_edit: bool):
        fun = uam.can_edit_existing_group

        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        root = get_root_group()

        # Deliberately chose a group that is not `Org` because that means the
        # `allow_org_edit` must have no effect.
        group = make_group(name="not-Org")

        # Must not throw an error if we do not pass a group.
        fun(db, group.owner, None, allow_org_edit=org_edit)

        # Root user and group owners must have access and thus not raise an exception.
        fun(db, root.owner, group, allow_org_edit=org_edit)
        fun(db, group.owner, group, allow_org_edit=org_edit)

        # Must reject all other users with 403.
        with pytest.raises(HTTPException) as err:
            fun(db, group.owner + "invalid", group, allow_org_edit=org_edit)
        assert err.value.status_code == 403

        # Set the root owner to empty and verify that no backdoor exists.
        set_root_group("")
        with pytest.raises(HTTPException) as err:
            fun(db, "", group, allow_org_edit=org_edit)

        # If the root user is "*" then everyone can edit.
        set_root_group("*")
        fun(db, "", group, allow_org_edit=org_edit)

    def test_can_edit_existing_group_org_edit(self):
        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        root = get_root_group()

        # Deliberately choose the root group for this example because it is the
        # only group on which the `allow_org_edit` option has an effect.
        group = make_group(name="Org")

        # Must not throw an error if we do not pass a group.
        uam.can_edit_existing_group(db, group.owner, None, allow_org_edit=False)

        # Even root must not have access.
        with pytest.raises(HTTPException) as err:
            uam.can_edit_existing_group(db, root.owner, group, allow_org_edit=False)
        assert err.value.status_code == 422

        with pytest.raises(HTTPException) as err:
            uam.can_edit_existing_group(db, group.owner, group, allow_org_edit=False)
        assert err.value.status_code == 422

    def test_can_edit_existing_group_missing_org(self):
        _, db, _, err = deps.create_spanner_client()
        assert not err and db
        group = make_group()

        uam.can_edit_existing_group(db, group.owner, group, allow_org_edit=True)

        with db.batch() as batch:
            batch.delete(table="OrgGroups", keyset=spanner.KeySet([["Org"]]))

        with pytest.raises(HTTPException) as err:
            uam.can_edit_existing_group(db, group.owner, group, allow_org_edit=True)
        assert err.value.status_code == 500

    def test_put_group(self):
        user1, user2 = "user-1@org.com", "user-2@org.com"
        c_root = create_root_client("/demo/api/uam/v1")
        c_user1 = create_root_client("/demo/api/uam/v1", user1)
        c_user2 = create_root_client("/demo/api/uam/v1", user2)

        # Create a group and user.
        group, user = make_group(name="foo", owner=user1), make_user()
        assert c_user1.post("/groups", json=group.model_dump()).status_code == 201
        assert c_user1.post("/users", json=user.model_dump()).status_code == 201

        # Update the group as root user must succeed.
        assert c_root.put("/groups", json=group.model_dump()).status_code == 204

        # Update the group as owner must succeed.
        assert c_user1.put("/groups", json=group.model_dump()).status_code == 204

        # Update group as any other user must fail.
        assert c_user2.put("/groups", json=group.model_dump()).status_code == 403

    def test_delete_group(self):
        user1, user2 = "user-1@org.com", "user-2@org.com"
        c_root = create_root_client("/demo/api/uam/v1")
        c_user1 = create_root_client("/demo/api/uam/v1", user1)
        c_user2 = create_root_client("/demo/api/uam/v1", user2)

        # Create a group.
        group = make_group(owner=user1)
        assert c_root.post("/groups", json=group.model_dump()).status_code == 201

        assert len(get_groups(c_root)) == 1

        # Must not process request from random user.
        assert c_user2.delete(f"/groups/{group.name}").status_code == 403
        assert len(get_groups(c_root)) == 1

        # Must allow the group owner to delete the group.
        assert c_user1.delete(f"/groups/{group.name}").status_code == 204
        assert len(get_groups(c_root)) == 0

    def test_update_group_users(self):
        user1, user2 = "user-1@org.com", "user-2@org.com"
        c_root = create_root_client("/demo/api/uam/v1")
        c_user1 = create_root_client("/demo/api/uam/v1", user1)
        c_user2 = create_root_client("/demo/api/uam/v1", user2)

        # Create a group and a user.
        group, user = make_group(owner=user1), make_user()
        assert c_root.post("/groups", json=group.model_dump()).status_code == 201
        assert c_root.post("/users", json=user.model_dump()).status_code == 201

        url = f"/groups/{group.name}/users"

        # Random user must not be able to update the users of a group.
        assert c_user2.put(url, json=[user.email]).status_code == 403
        groups = get_groups(c_root)
        assert len(groups) == 1 and len(groups[0].users) == 0

        # Group owner must be able to update the users of a group.
        assert c_user1.put(url, json=[user.email]).status_code == 201
        groups = get_groups(c_root)
        assert len(groups) == 1 and len(groups[0].users) == 1

    def test_update_group_roles(self):
        user1, user2 = "user-1@org.com", "user-2@org.com"
        c_root = create_root_client("/demo/api/uam/v1")
        c_user1 = create_root_client("/demo/api/uam/v1", user1)
        c_user2 = create_root_client("/demo/api/uam/v1", user2)

        # Create a group.
        group = make_group(owner=user1)
        assert c_root.post("/groups", json=group.model_dump()).status_code == 201

        url = f"/groups/{group.name}/roles"
        roles: UAMRoles = ["role-1", "role-2"]

        # Random user must not be able to update the roles of a group.
        assert c_user2.put(url, json=roles).status_code == 403
        groups = get_groups(c_root)
        assert len(groups) == 1 and len(groups[0].roles) == 0

        # Group owner must be able to update the roles of a group.
        assert c_user1.put(url, json=roles).status_code == 201
        groups = get_groups(c_root)
        assert len(groups) == 1 and len(groups[0].roles) == 2

    def test_update_group_children(self):
        user1, user2 = "user-1@org.com", "user-2@org.com"
        c_root = create_root_client("/demo/api/uam/v1")
        c_user1 = create_root_client("/demo/api/uam/v1", user1)
        c_user2 = create_root_client("/demo/api/uam/v1", user2)

        # Create a group and a user.
        group_1, group_2 = sorted(
            [make_group(owner=user1), make_group(owner=user1)], key=lambda _: _.name
        )
        assert c_root.post("/groups", json=group_1.model_dump()).status_code == 201
        assert c_root.post("/groups", json=group_2.model_dump()).status_code == 201
        child = UAMChild(child=group_2.name).model_dump()

        url = f"/groups/{group_1.name}/children"

        # Random user must not be able to add child groups.
        assert c_user2.put(url, json=child).status_code == 403
        groups = get_groups(c_root)
        assert len(groups) == 2
        assert len(groups[0].children) == 0
        assert len(groups[1].children) == 0

        # Group owner must be able to add child groups.
        assert c_user1.put(url, json=child).status_code == 201
        groups = get_groups(c_root)
        assert len(groups) == 2
        assert len(groups[0].children) == 1
        assert len(groups[1].children) == 0

        # ----------------------------------------------------------------------
        # Unlink Children.
        # ----------------------------------------------------------------------
        url = f"/groups/{group_1.name}/children/{group_2.name}"

        # Random user must be unable to unlink a child.
        assert c_user2.delete(url).status_code == 403
        groups = get_groups(c_root)
        assert len(groups) == 2
        assert len(groups[0].children) == 1
        assert len(groups[1].children) == 0

        # Group owner user must able to unlink a child.
        assert c_user1.delete(url).status_code == 204
        groups = get_groups(c_root)
        assert len(groups) == 2
        assert len(groups[0].children) == 0
        assert len(groups[1].children) == 0
