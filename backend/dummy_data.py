import os
import random
from typing import Dict, Set, Tuple

import faker
import httpx
from tqdm import tqdm

import dfh.api
import dfh.routers.auth as auth
import tests.conftest
from dfh.models import UAMChild, UAMGroup, UAMUser
from tests.test_helpers import set_root_user


def create_hierarchy(
    nname: str, available: Set[str], prob: float, all_groups: Dict[str, UAMGroup]
):
    if len(available) == 0:  # codecov-skip
        return

    node = all_groups[nname]
    available.discard(nname)

    cur = {_ for _ in available if random.random() < prob}
    node.children = list(cur)
    available -= cur

    for child in node.children:
        create_hierarchy(child, available, prob / 2.0, all_groups)


def create_fake_uam_dataset() -> Tuple[Dict[str, UAMUser], Dict[str, UAMGroup]]:
    # Do nothing unless we are running in local developer mode.
    assert dfh.api.isLocalDev()

    num_users, num_groups = 100, 100
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

    all_users: Dict[str, UAMUser] = {}
    for idx in range(len(names)):
        user = UAMUser(
            name=str.join(" ", names[idx]),
            lanid=lanids[idx],
            slack=slack[idx],
            email=all_emails[idx],
            role="Engineer",
            manager=random.choice(all_emails),
        )
        all_users[user.email] = user
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

    groups: Dict[str, UAMGroup] = {}
    for group_name in group_names:
        k = random.randint(0, num_users // 2)
        emails = list(set(random.choices(all_emails, k=k)))
        owner = emails[0] if len(emails) > 0 else all_emails[0]

        roles = random.choices(role_pool, k=random.randint(0, 5))
        groups[group_name] = UAMGroup(
            name=group_name,
            users=emails,
            provider=random.choice(["google", "github"]),
            owner=owner,
            roles=list(set(roles)),
        )
        del k, emails, owner, group_name

    groups["Org"] = UAMGroup(name="Org", owner="foo", provider="foo")
    return all_users, groups


def publish_hierarchy(
    client: httpx.Client, nname: str, all_groups: Dict[str, UAMGroup]
):
    print(".", end="", flush=True)
    url = f"/uam/v1/groups/{nname}/children"
    for child in all_groups[nname].children:
        resp = client.put(url, json=UAMChild(child=child).model_dump())
        assert resp.status_code == 201, (resp, resp.json())
        publish_hierarchy(client, child, all_groups)


def main():
    tests.conftest.create_spanner_tables()
    set_root_user(os.environ["DFH_ROOT"])

    users, groups = create_fake_uam_dataset()

    available = set(groups)
    create_hierarchy("Org", available, 0.1, groups)

    token = auth.mint_token("foo@bar.com", "token-key-from-gsm")
    headers = {"Authorization": f"Bearer {token.token}"}
    base_url = "http://localhost:5001/demo/api"

    with httpx.Client(headers=headers, base_url=base_url) as client:
        resp = client.get("/auth/users/me")
        print(resp.json())
        assert resp.status_code == 200

        for user in tqdm(users.values(), desc="creating users "):
            resp = client.post("/uam/v1/users", json=user.model_dump())
            assert resp.status_code == 201, (resp, resp.json())

        for group in tqdm(groups.values(), desc="creating groups"):
            if group.name != "Org":
                resp = client.post("/uam/v1/groups", json=group.model_dump())
                assert resp.status_code == 201, (resp, resp.json())

            roles = list(group.users)
            resp = client.put(f"/uam/v1/groups/{group.name}/users", json=roles)
            assert resp.status_code == 201, (resp, resp.json())
            del roles

            resp = client.put(f"/uam/v1/groups/{group.name}/roles", json=group.roles)
            assert resp.status_code == 201, (resp, resp.json())

        publish_hierarchy(client, "Org", groups)


if __name__ == "__main__":
    main()
