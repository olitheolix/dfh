import random
from typing import Annotated, Dict, List, Set, Tuple
from collections import defaultdict

import faker
from fastapi import APIRouter, Depends, HTTPException, status

import dfh.api
import dfh.routers.dependencies
from dfh.models import UAMRoles, UAMChild, UAMGroup, UAMUser, UAMRoles, UAMUserRoles

from .dependencies import is_authenticated

# Convenience.
UAM_DB = dfh.routers.dependencies.UAM_DB
RESPONSE_404 = {"description": "not found", "model": UAMChild}
RESPONSE_409 = {"description": "already exists", "model": UAMChild}

router = APIRouter()
d_user = Annotated[str, Depends(is_authenticated)]


def can_edit_group(user: str, group: UAMGroup | None):
    """FastAPI to fixture to determine if a user has edit rights on the group.

    Only the group owners and root will pass the test.

    """
    # Request handler needs to decide what do here.
    if not group:
        return

    # Special case: everybody is root.
    if UAM_DB.root.owner == "*":
        return

    # Root user always has EDIT permissions.
    if UAM_DB.root.owner and user == UAM_DB.root.owner:
        return

    # Group owner has EDIT permissions.
    if user == group.owner:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient permissions")


def create_fake_uam_dataset():
    # Do nothing unless we are running in local developer mode.
    if not dfh.api.isLocalDev():
        return

    num_users, num_groups = 1000, 100
    fake = faker.Faker()
    first = [fake.first_name() for _ in range(num_users)]
    last = [fake.last_name().split()[0] for _ in range(num_users)]
    names = list(set(zip(first, last)))
    all_emails = [f"{f}.{s}@foo.org" for f, s in names]
    all_emails = [_.lower() for _ in all_emails]
    assert len(all_emails) == len(set(all_emails)), "email"
    lanids = [f"{f_[0]}{l_[:4]}" for f_, l_ in names]
    slack = [f"@{f_[0]}{l_[:4]}" for f_, l_ in names]
    del first, last

    group_names = [str.join("-", fake.country().split()) for _ in range(num_groups)]
    group_names = list(set(group_names))

    for idx in range(len(names)):
        UAM_DB.users[all_emails[idx]] = UAMUser(
            name=str.join(" ", names[idx]),
            lanid=lanids[idx],
            slack=slack[idx],
            email=all_emails[idx],
            role="Engineer",
            manager=random.choice(all_emails),
        )
        del idx

    role_pool = [
        "roles/bigquery.dataViewer",
        "roles/bigquery.user",
        "roles/cloudsql.admin",
        "roles/compute.networkAdmin",
        "roles/compute.viewer",
        "roles/datastore.user",
        "roles/editor",
        "roles/iam.roleViewer",
        "roles/iam.serviceAccountUser",
        "roles/logging.logWriter",
        "roles/logging.viewer",
        "roles/ml.admin",
        "roles/owner",
        "roles/pubsub.editor",
        "roles/pubsub.viewer",
        "roles/secretmanager.secretAccessor",
        "roles/spanner.databaseUser",
        "roles/storage.admin",
        "roles/storage.objectViewer",
        "roles/viewer",
    ]

    for group_name in group_names:
        k = random.randint(0, num_users // 2)
        emails = list(set(random.choices(all_emails, k=k)))
        users = {_: UAM_DB.users[_] for _ in emails}
        owner = emails[0] if len(emails) > 0 else all_emails[0]

        roles = random.choices(role_pool, k=random.randint(0, 5))
        UAM_DB.groups[group_name] = UAMGroup(
            name=group_name,
            users=users,
            provider=random.choice(["google", "github"]),
            owner=owner,
            roles=list(set(roles)),
        )
        del k, emails, users, owner, group_name
    del group_names

    create_hierarchy(UAM_DB.root, set(UAM_DB.groups), 0.1)


def create_hierarchy(node: UAMGroup, available: Set[str], prob: float):
    if len(available) == 0:  # codecov-skip
        return

    cur = {_ for _ in available if random.random() < prob}
    node.children = {name: UAM_DB.groups[name] for name in cur}
    available -= cur

    for child in node.children.values():
        create_hierarchy(child, available, prob / 2.0)


@router.get("/v1/groups", status_code=status.HTTP_200_OK)
def get_groups() -> List[UAMGroup]:
    """Return all known groups."""
    return sorted(UAM_DB.groups.values(), key=lambda _: _.name)


@router.post(
    "/v1/groups",
    status_code=status.HTTP_201_CREATED,
    responses={409: RESPONSE_409},
)
def post_group(group: UAMGroup):
    """Create a new group. Returns 409 if the group already exists."""
    # Special case: abort immediately if the group name matches the root group name.
    if group.name == UAM_DB.root.name:
        raise HTTPException(status_code=422, detail="cannot create root group")

    # Return an error if a group with that name already exists.
    if group.name in UAM_DB.groups:
        raise HTTPException(
            status_code=409, detail=f"group <{group.name}> already exists"
        )

    # Clear users and children.
    # fixme: allow to specify members and children but need sanity checks that
    # those users and children exist.
    group.users.clear()
    group.children.clear()

    # Add the group to our DB.
    UAM_DB.groups[group.name] = group


@router.put(
    "/v1/groups",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: RESPONSE_404},
)
def put_group(user: d_user, group: UAMGroup):
    """Update an existing group. Returns 404 if the group does not exist.

    NOTE: this will only allow to change the owner and description. All other
    fields will be ignored.

    """
    # Special case: abort immediately if the group name matches the root group name.
    if group.name == UAM_DB.root.name:
        raise HTTPException(status_code=422, detail="cannot update root group")

    # Return an error if a group with that name already exists.
    if group.name not in UAM_DB.groups:
        raise HTTPException(
            status_code=404, detail=f"group <{group.name}> does not exist"
        )

    # Authorisation check.
    can_edit_group(user, group)

    # Update the group in our DB.
    UAM_DB.groups[group.name].owner = group.owner
    UAM_DB.groups[group.name].description = group.description


@router.put(
    "/v1/groups/{name}/roles",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404},
)
def set_group_permissions(user: d_user, name: str, roles: UAMRoles):
    """Sets the permissions of the group. The new permissions are canonical."""
    try:
        group = UAM_DB.groups[name]
    except KeyError:
        raise HTTPException(status_code=404, detail="group not found")

    # Authorisation check.
    can_edit_group(user, group)

    # De-duplicate the new roles and assign them to the group.
    group.roles = list(sorted(set(roles)))


@router.get(
    "/v1/groups/{name}",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
def get_group(name: str) -> UAMGroup:
    """Return the specific group."""
    try:
        return UAM_DB.groups[name]
    except KeyError:
        raise HTTPException(status_code=404, detail="group not found")


@router.delete("/v1/groups/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(user: d_user, name: str):
    """Remove the group from the database.

    NOTE: This will not remove any users from the database.

    """
    # Special case: abort immediately if the group name matches the root group name.
    if name == UAM_DB.root.name:
        raise HTTPException(status_code=422, detail="cannot delete root group")

    can_edit_group(user, UAM_DB.groups.get(name, None))

    UAM_DB.groups.pop(name, None)
    UAM_DB.root.children.pop(name, None)

    for group in UAM_DB.groups.values():
        group.children.pop(name, None)


@router.put(
    "/v1/groups/{name}/users",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404},
)
def put_group_members(user: d_user, name: str, emails: List[str]):
    """Set the users of the group.

    The supplied email list is canonical and will replace the existing users of
    that list.

    This endpoint does nothing unless all `emails` exist.

    """
    if name not in UAM_DB.groups:
        raise HTTPException(status_code=404, detail="group not found")

    can_edit_group(user, UAM_DB.groups[name])

    try:
        users = {email: UAM_DB.users[email] for email in emails}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"user {e} not found")

    UAM_DB.groups[name].users = users


@router.put(
    "/v1/groups/{name}/children",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404, 409: RESPONSE_409},
)
def put_add_child_group(user: d_user, name: str, new: UAMChild):
    """Nest an existing group inside another group.

    Returns 409 if the new group would create a cycle.

    """
    try:
        parent = UAM_DB.root if name == UAM_DB.root.name else UAM_DB.groups[name]
        child = UAM_DB.groups[new.child]
    except KeyError:
        raise HTTPException(status_code=404, detail="group not found")

    can_edit_group(user, parent)

    def is_descendant(pname: str, node: UAMGroup) -> bool:
        if node.name == pname:
            return True
        out = False
        for child in node.children.values():
            out |= is_descendant(pname, child)
        return out

    # Ensure the descendants of the child do not contain the parent.
    if is_descendant(parent.name, child):
        raise HTTPException(status_code=409, detail="parent is a descendant of child")

    parent.children[child.name] = child


@router.delete(
    "/v1/groups/{parent}/children/{child}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: RESPONSE_404},
)
def unlink_child_from_group(user: d_user, parent: str, child: str):
    """Unlink the specified child group from its parent.

    This does *not* delete the group, only remove it as a child of the parent group.

    """
    try:
        group = UAM_DB.root if parent == UAM_DB.root.name else UAM_DB.groups[parent]
    except KeyError:
        raise HTTPException(status_code=404, detail="group not found")

    can_edit_group(user, group)
    group.children.pop(child, None)


@router.get(
    "/v1/groups/{name}/users",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
def get_users_in_group(name: str, recursive: bool = False) -> List[UAMUser]:
    """Return all users in the group.

    Use `recursive=True` to include all users in all sub-groups.

    """
    # Find the group.
    try:
        group = UAM_DB.groups[name]
    except KeyError:
        # Special case: group might be the root group which is not part of the
        # hierarchy in the DB since its root status is immutable.
        if name == UAM_DB.root.name:
            group = UAM_DB.root
        else:
            raise HTTPException(status_code=404, detail="group not found")

    users: Dict[str, UAMUser] = {}

    def _walk(node: UAMGroup):
        users.update(node.users)
        for child in node.children.values():
            _walk(child)

    # Either compile users recursively or collect them just from this group.
    if recursive:
        _walk(group)
    else:
        users = group.users

    return sorted(users.values(), key=lambda _: _.name)


@router.get("/v1/users", status_code=status.HTTP_200_OK)
def get_user() -> List[UAMUser]:
    """Return list of all users in the system."""
    return [UAM_DB.users[_] for _ in sorted(UAM_DB.users)]


@router.post(
    "/v1/users", status_code=status.HTTP_201_CREATED, responses={409: RESPONSE_409}
)
def post_user(user: UAMUser):
    """Create new user."""
    if user.email in UAM_DB.users:
        raise HTTPException(status_code=409, detail="user already exists")
    UAM_DB.users[user.email] = user


@router.get(
    "/v1/users/{user}", status_code=status.HTTP_200_OK, responses={404: RESPONSE_404}
)
def get_single_user(user: str) -> UAMUser:
    """Return a single user."""
    try:
        return UAM_DB.users[user]
    except KeyError:
        raise HTTPException(status_code=404, detail="user not found")


@router.delete("/v1/users/{user}", status_code=status.HTTP_204_NO_CONTENT)
def delete_users(user: str):
    """Remove user from system.

    This will also remove the user from all the groups it was a member of.

    """
    UAM_DB.users.pop(user, None)
    for group in UAM_DB.groups.values():
        group.users.pop(user, None)


@router.get(
    "/v1/users/{username}/roles",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
def get_user_permissions(username: str) -> UAMUserRoles:
    """Returns all the permissions a user has inherited from its various group memberships."""
    try:
        UAM_DB.users[username]
    except KeyError:
        raise HTTPException(status_code=404, detail="user not found")

    # ----------------------------------------------------------------------
    # Traverse the entire tree and track the parent nodes as we do so.
    # Whenever we find the user in question we add all the parent groups to the
    # pool. This will leave us with the set of group nodes that have the user
    # in question as one of their descendants.
    # ----------------------------------------------------------------------
    group_pool: Set[str] = set()

    def walk(group: UAMGroup, parents: List[str]):
        parents.append(group.name)
        members = {_.email for _ in group.users.values()}
        if username in members:
            group_pool.update(parents)
        for child in group.children.values():
            walk(child, parents)
        parents.pop()

    walk(UAM_DB.root, [])
    del username

    # ----------------------------------------------------------------------
    # Compile the union of all roles from all groups.
    # ----------------------------------------------------------------------
    perms = defaultdict(list)

    for name in group_pool:
        group = UAM_DB.root if name == UAM_DB.root.name else UAM_DB.groups[name]
        for role in group.roles:
            perms[role].append(group.name)

    # ----------------------------------------------------------------------
    # Sort the role sources alphabetically and return.
    # ----------------------------------------------------------------------
    ret = UAMUserRoles(inherited={})
    for role, sources in perms.items():
        ret.inherited[role] = list(set(sources))

    return ret


@router.get("/v1/tree", status_code=status.HTTP_200_OK)
def get_tree() -> UAMGroup:
    """Return the group hierarchy but without any users in it to save space.

    This endpoint supports the tree view of groups in the frontend.

    """

    def walk(node: UAMGroup) -> UAMGroup:
        out = node.model_copy(deep=True)
        out.users = {}
        for name, child in node.children.items():
            out.children[name] = walk(child)
        return out

    return walk(UAM_DB.root)
