import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import APIRouter, HTTPException, status
from google.cloud import spanner
from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.transaction import Transaction

from dfh.models import (
    UAMChild,
    UAMGroup,
    UAMRoles,
    UAMTreeInfo,
    UAMTreeNode,
    UAMUser,
    UAMUserRoles,
)

from .dependencies import ROOT_NAME, d_db, d_user, handle_spanner_exceptions

# Convenience.
RESPONSE_404 = {"description": "not found", "model": UAMChild}
RESPONSE_409 = {"description": "already exists", "model": UAMChild}

router = APIRouter()
logit = logging.getLogger("app")


async def run_async(fun, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fun, *args, **kwargs)


def group_must_exist(db: Database, name: str) -> UAMGroup:
    return spanner_get_group(db, name)


def user_must_exist(db: Database, name: str) -> UAMUser:
    return spanner_get_user(db, name)


def can_edit_existing_group(db: Database, user: str, group: UAMGroup | None):
    """FastAPI to fixture to determine if a user has edit rights on the group.

    Only the group owners and root will pass the test.

    """
    # The caller needs to decide what to do here.
    if not group:
        return

    # Fetch root users.
    with db.snapshot() as snapshot:
        rows = snapshot.read(
            table="OrgRootUsers", columns=["email"], keyset=spanner.KeySet(all_=True)
        )
        root_users = {_[0] for _ in rows if _[0] != ""}

    # Root users always have EDIT permissions.
    if user in root_users:
        return

    # Special case: everybody is root.
    if "*" in root_users:
        return

    # Group owner has EDIT permissions.
    if user == group.owner:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient permissions")


@router.get("/v1/groups", status_code=status.HTTP_200_OK)
async def get_groups(db: d_db) -> List[UAMGroup]:
    """Return all known groups."""
    groups = await run_async(spanner_get_all_groups, db)
    return [_ for _ in groups.values() if _.name != "Org"]


@router.post(
    "/v1/groups",
    status_code=status.HTTP_201_CREATED,
    responses={409: RESPONSE_409},
)
async def post_group(db: d_db, group: UAMGroup):
    """Create a new group. Returns 409 if the group already exists."""
    # Special case: abort immediately if the group name matches the root group name.
    if group.name == ROOT_NAME:
        raise HTTPException(status_code=422, detail="cannot create <Org> group")

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.insert(
                table="OrgGroups",
                columns=("email", "owner", "provider", "description"),
                values=[(group.name, group.owner, group.provider, group.description)],
            )

    await run_async(work)


@router.put(
    "/v1/groups",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: RESPONSE_404},
)
async def put_group(db: d_db, user: d_user, group: UAMGroup):
    """Update an existing group. Returns 404 if the group does not exist.

    NOTE: this will only allow to change the owner and description. All other
    fields will be ignored.

    """
    group_must_exist(db, group.name)
    can_edit_existing_group(db, user, group)

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.update(
                table="OrgGroups",
                columns=["email", "owner", "description"],
                values=[(group.name, group.owner, group.description)],
            )

    await run_async(work)


@router.put(
    "/v1/groups/{name}/roles",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404},
)
async def set_group_permissions(user: d_user, db: d_db, name: str, roles: UAMRoles):
    """Sets the permissions of the group. The new permissions are canonical."""
    # Authorisation check.
    group = group_must_exist(db, name)
    can_edit_existing_group(db, user, group)

    roles = list(sorted(set(roles)))

    def work():
        with db.batch() as batch:
            batch.insert_or_update(
                table="OrgGroupsRoles",
                columns=("group_id", "roles"),
                values=[(group.name, roles)],
            )

    await run_async(work)


@router.get(
    "/v1/groups/{name}",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
async def get_group(db: d_db, name: str) -> UAMGroup:
    """Return the specific group."""
    return await run_async(spanner_make_group, db, name)


@router.delete("/v1/groups/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(user: d_user, db: d_db, name: str):
    """Remove the group from the database.

    NOTE: This will not remove any users from the database.

    """
    if name == ROOT_NAME:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="cannot delete <Org> group"
        )

    # Fetch the group. Do nothing if the group does not exist.
    try:
        group = await run_async(spanner_get_group, db, name)
    except HTTPException:
        return

    can_edit_existing_group(db, user, group)

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.delete(table="OrgGroups", keyset=spanner.KeySet([[name]]))

    await run_async(work)


@router.put(
    "/v1/groups/{name}/users",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404},
)
async def put_group_members(user: d_user, db: d_db, name: str, emails: List[str]):
    """Set the users of the group.

    The supplied email list is canonical and will replace the existing users of
    that list.

    This endpoint does nothing unless all `emails` exist.

    """
    if len(emails) == 0:
        return

    group = group_must_exist(db, name)
    can_edit_existing_group(db, user, group)

    # Abort unless all emails exist in our database.
    all_users = spanner_get_all_users(db)
    try:
        users = {email: all_users[email] for email in emails}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"user {e} not found")

    def sync_users(transaction: Transaction):
        # 1. Remove users from the group who are NOT in the given list
        delete_query = """
            DELETE FROM OrgGroupsUsers
            WHERE group_id = @group_id AND user_id NOT IN UNNEST(@user_list)
        """
        transaction.execute_update(
            delete_query,
            params={"group_id": name, "user_list": list(users)},
            param_types={
                "group_id": spanner.param_types.STRING,
                "user_list": spanner.param_types.Array(spanner.param_types.STRING),
            },
        )

        rows_to_insert = [(name, user_id) for user_id in users]
        transaction.insert_or_update(
            table="OrgGroupsUsers",
            columns=("group_id", "user_id"),
            values=rows_to_insert,
        )

    await run_async(handle_spanner_exceptions(db.run_in_transaction), sync_users)


@router.put(
    "/v1/groups/{name}/children",
    status_code=status.HTTP_201_CREATED,
    responses={404: RESPONSE_404, 409: RESPONSE_409},
)
async def put_add_child_group(db: d_db, user: d_user, name: str, new: UAMChild):
    """Nest an existing group inside another group.

    Returns 409 if the new group would create a cycle.

    """
    parent = group_must_exist(db, name)
    can_edit_existing_group(db, user, parent)

    all_groups = await run_async(spanner_get_all_groups, db)

    def is_descendant(pname: str, node_name: str) -> bool:
        if node_name == pname:
            return True

        ret = False
        for child_name in all_groups[node_name].children:
            ret |= is_descendant(pname, child_name)
        return ret

    child = await run_async(spanner_make_group, db, new.child)

    if is_descendant(parent.name, new.child):
        raise HTTPException(status_code=409, detail="parent is a descendant of child")

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.insert_or_update(
                table="OrgGroupsGroups",
                columns=["parent_id", "child_id"],
                values=[(parent.name, child.name)],
            )

    await run_async(work)


@router.delete(
    "/v1/groups/{parent}/children/{child}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: RESPONSE_404},
)
async def unlink_child_from_group(db: d_db, user: d_user, parent: str, child: str):
    """Unlink the specified child group from its parent.

    This does *not* delete the group, only remove it as a child of the parent group.

    """
    group = group_must_exist(db, parent)
    can_edit_existing_group(db, user, group)

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.delete(
                table="OrgGroupsGroups", keyset=spanner.KeySet([[parent, child]])
            )

    await run_async(work)


@router.get(
    "/v1/groups/{name}/users",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
async def get_users_in_group(
    db: d_db, name: str, recursive: bool = False
) -> List[UAMUser]:
    """Return all users in the group.

    Use `recursive=True` to include all users in all sub-groups.

    """
    all_groups = spanner_get_all_groups(db)
    all_users = spanner_get_all_users(db)

    if name not in all_groups:
        raise HTTPException(status_code=404, detail="group not found")

    users: Dict[str, UAMUser] = {}

    def _walk(gname: str):
        group = all_groups[gname]
        tmp = {_: all_users[_] for _ in group.users}

        users.update(tmp)
        for child in group.children:
            _walk(child)

    # Either compile users recursively or collect them just from this group.
    if recursive:
        _walk(name)
    else:
        users = {all_users[_].email: all_users[_] for _ in all_groups[name].users}

    return sorted(users.values(), key=lambda _: _.name)


@router.get("/v1/users", status_code=status.HTTP_200_OK)
async def get_user(db: d_db) -> List[UAMUser]:
    """Return list of all users in the system."""
    users = await run_async(spanner_get_all_users, db)
    return list(sorted(users.values(), key=lambda _: _.email))


@router.post(
    "/v1/users", status_code=status.HTTP_201_CREATED, responses={409: RESPONSE_409}
)
async def post_user(user: UAMUser, db: d_db):
    """Create new user."""
    cols = ["email", "name", "lanid", "slack", "role", "manager"]
    values = (user.email, user.name, user.lanid, user.slack, user.role, user.manager)

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.insert(table="OrgUsers", columns=cols, values=[values])

    await run_async(work)


@router.get(
    "/v1/users/{user}", status_code=status.HTTP_200_OK, responses={404: RESPONSE_404}
)
async def get_single_user(user: str, db: d_db) -> UAMUser:
    """Return a single user."""
    return await run_async(spanner_get_user, db, user)


@router.delete("/v1/users/{user}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_users(user: str, db: d_db):
    """Remove user from system.

    This will also remove the user from all the groups it was a member of.

    """

    @handle_spanner_exceptions
    def work():
        with db.batch() as batch:
            batch.delete(table="OrgUsers", keyset=spanner.KeySet(keys=[(user,)]))

    return await run_async(work)


@router.get(
    "/v1/users/{username}/roles",
    status_code=status.HTTP_200_OK,
    responses={404: RESPONSE_404},
)
async def get_user_permissions(db: d_db, username: str) -> UAMUserRoles:
    """Returns all the permissions a user has inherited from its various group memberships."""
    user_must_exist(db, username)

    @handle_spanner_exceptions
    def work():
        with db.snapshot() as snapshot:
            cols = ["group_id", "roles"]
            rows = snapshot.read(
                table="OrgGroupsRoles",
                columns=cols,
                keyset=spanner.KeySet(all_=True),
            )
            group_roles = {_[0]: _[1] for _ in rows}

        all_groups = spanner_get_all_groups(db)
        return all_groups, group_roles

    all_groups, group_roles = await run_async(work)

    # ----------------------------------------------------------------------
    # Traverse the entire tree and track the parent nodes as we do so.
    # Whenever we find the user in question we add all the parent groups to the
    # pool. This will leave us with the set of group nodes that have the user
    # in question as one of their descendants.
    # ----------------------------------------------------------------------
    group_pool: Set[str] = set()

    def walk(gname: str, parents: List[str]):
        parents.append(gname)
        members = set(all_groups[gname].users)
        if username in members:
            group_pool.update(parents)
        for child in all_groups[gname].children:
            walk(child, parents)
        parents.pop()

    walk("Org", [])
    del username

    # ----------------------------------------------------------------------
    # Compile the union of all roles from all groups.
    # ----------------------------------------------------------------------
    perms = defaultdict(list)

    for name in group_pool:
        for role in group_roles.get(name, []):
            perms[role].append(name)

    # ----------------------------------------------------------------------
    # Sort the role sources alphabetically and return.
    # ----------------------------------------------------------------------
    ret = UAMUserRoles(inherited={})
    for role, sources in perms.items():
        ret.inherited[role] = list(set(sources))

    return ret


@router.get("/v1/tree", status_code=status.HTTP_200_OK)
async def get_tree(db: d_db) -> UAMTreeInfo:
    """Return the group hierarchy but without any users in it to save space.

    This endpoint supports the tree view of groups in the frontend.

    """
    all_groups = await run_async(spanner_get_all_groups, db)

    groups: Dict[str, UAMGroup] = {}

    def _walk(gname: str) -> UAMTreeNode:
        groups[gname] = all_groups[gname]
        node = UAMTreeNode(name=gname)
        for child_name in all_groups[gname].children:
            node.children[child_name] = _walk(child_name)
        return node

    tree = _walk("Org")
    return UAMTreeInfo(groups=groups, root=tree)


@handle_spanner_exceptions
def spanner_get_group(db: Database, group_name: str) -> UAMGroup:
    with db.snapshot() as snapshot:
        cols = ["email", "owner", "provider", "description"]
        rows = snapshot.read(
            table="OrgGroups",
            columns=cols,
            keyset=spanner.KeySet([[group_name]]),
        )
        rows = list(rows)

    if len(rows) != 1:
        raise HTTPException(status_code=404, detail=f"group {group_name} not found")

    # fixme: change UAM.name -> UAM.email
    cols[0] = "name"
    return UAMGroup.model_validate(dict(zip(cols, rows[0])))


@handle_spanner_exceptions
def spanner_get_all_groups(db: Database) -> Dict[str, UAMGroup]:
    def work(transaction: Transaction):
        # Fetch all group roles.
        cols = ["group_id", "roles"]
        rows = transaction.read(
            table="OrgGroupsRoles",
            columns=cols,
            keyset=spanner.KeySet(all_=True),
        )
        rows = list(rows)
        group_roles = {}
        for gid, roles in rows:
            group_roles[gid] = roles

        # Fetch all group - user relations.
        cols = ["group_id", "user_id"]
        rows = transaction.read(
            table="OrgGroupsUsers",
            columns=cols,
            keyset=spanner.KeySet(all_=True),
        )
        rows = list(rows)
        users_per_group = defaultdict(list)
        for parent, child in rows:
            users_per_group[parent].append(child)

        # Fetch all group - group relations.
        cols = ["parent_id", "child_id"]
        rows = transaction.read(
            table="OrgGroupsGroups",
            columns=cols,
            keyset=spanner.KeySet(all_=True),
        )
        rows = list(rows)
        groups_per_group = defaultdict(list)
        for parent, child in rows:
            groups_per_group[parent].append(child)

        cols = ["email", "owner", "provider", "description"]
        rows = transaction.read(
            table="OrgGroups",
            columns=cols,
            keyset=spanner.KeySet(all_=True),
        )
        rows = list(rows)

        # fixme: change UAM.name -> UAM.email
        cols[0] = "name"
        tmp = [UAMGroup.model_validate(dict(zip(cols, row))) for row in rows]
        for i in tmp:
            i.users = users_per_group[i.name]
            i.children = groups_per_group[i.name]
            i.roles = group_roles.get(i.name, [])

        groups = {_.name: _ for _ in tmp}
        return groups

    return db.run_in_transaction(work)


@handle_spanner_exceptions
def spanner_get_user(db: Database, user_name: str) -> UAMUser:
    cols = ["email", "name", "lanid", "slack", "role", "manager"]
    with db.snapshot() as snapshot:
        rows = snapshot.read(
            table="OrgUsers",
            columns=cols,
            keyset=spanner.KeySet([[user_name]]),
        )
        rows = list(rows)

    if len(rows) != 1:
        raise HTTPException(status_code=404, detail=f"user {user_name} not found")

    return UAMUser.model_validate(dict(zip(cols, rows[0])))


@handle_spanner_exceptions
def spanner_get_all_users(db: Database) -> Dict[str, UAMUser]:
    cols = ["email", "name", "lanid", "slack", "role", "manager"]
    with db.snapshot() as snapshot:
        rows = snapshot.read(
            table="OrgUsers",
            columns=cols,
            keyset=spanner.KeySet(all_=True),
        )
        rows = list(rows)

    tmp = [UAMUser.model_validate(dict(zip(cols, row))) for row in rows]
    users = {_.email: _ for _ in tmp}
    return users


@handle_spanner_exceptions
def spanner_make_group(db: Database, group_name: str) -> UAMGroup:
    group = group_must_exist(db, group_name)

    def work(transaction: Transaction) -> UAMGroup:
        # Find all roles.
        rows = transaction.execute_sql(
            "SELECT group_id, roles FROM OrgGroupsRoles WHERE group_id=@group",
            param_types={"group": spanner.param_types.STRING},
            params={"group": group_name},
        )
        rows = list(rows)
        roles = [] if len(rows) == 0 else rows[0][1]

        # --- Find all users in group.
        rows = transaction.execute_sql(
            "SELECT group_id, user_id FROM OrgGroupsUsers WHERE group_id=@group",
            param_types={"group": spanner.param_types.STRING},
            params={"group": group.name},
        )
        users: List[str] = [_[1] for _ in rows]
        group.users = users

        # --- Find all child groups.
        rows = transaction.execute_sql(
            "SELECT parent_id, child_id FROM OrgGroupsGroups WHERE parent_id=@group",
            param_types={"group": spanner.param_types.STRING},
            params={"group": group.name},
        )
        children = [_[1] for _ in rows]
        group.children = list(children)

        group.roles = roles
        return group

    return db.run_in_transaction(work)
