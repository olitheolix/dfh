import random
from typing import Annotated
import requests
import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Set, Dict

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import httplib2
import square.dtypes
import square.k8s
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from fastapi import FastAPI, HTTPException, Request, Response, status, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from square.square import DeploymentPlan
from starlette.middleware.sessions import SessionMiddleware

import dfh
import dfh.generate
import dfh.k8s
import dfh.square_types
import dfh.watch
from dfh.manifest_utilities import get_metainfo
from dfh.models import (
    AppEnvOverview,
    AppInfo,
    Database,
    DatabaseAppEntry,
    GoogleToken,
    JobDescription,
    JobStatus,
    PodList,
    ServerConfig,
    UAMTreeNode,
    UAMDatabase,
    UAMUser,
    UAMGroup,
    WatchedResource,
)

# Convenience.
logit = logging.getLogger("app")

UAM_DB: UAMDatabase = UAMDatabase(users=[], groups=[])


def isLocalDev() -> bool:
    return os.environ.get("LOCAL_DEV", "") != ""


# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client_secret.json"

# Specify the OAuth CLIENT_ID of the app from Google Cloud Console.
GOOGLE_CLIENT_ID = (
    "34471668497-aj0h4ifb4fe3dbcrijurdu04ahu1gurm.apps.googleusercontent.com"
)


# Request a token to query the user's email.
SCOPES = ["https://www.googleapis.com/auth/userinfo.email", "openid"]


def create_fake_uam_dataset():
    import faker

    num_users, num_groups = 1000, 1000
    fake = faker.Faker()
    first = [fake.first_name() for _ in range(num_users)]
    last = [fake.name().split()[0] for _ in range(num_users)]
    user_names = [f"{f}.{s}@company.org" for f, s in zip(first, last)]
    user_names = list(set(user_names))
    del first, last

    group_names = [str.join("-", fake.country().split()) for _ in range(num_groups)]
    group_names = list(set(group_names))

    for idx, user_name in enumerate(user_names):
        UAM_DB.users.append(UAMUser(name=user_name, uid=f"uid-{idx}"))
        del idx, user_name

    for idx, group_name in enumerate(group_names):
        k = random.randint(0, num_users // 2)
        user_idx = random.choices(range(len(UAM_DB.users)), k=k)
        user_idx = list(set(user_idx))
        users = [UAM_DB.users[_] for _ in user_idx]
        UAM_DB.groups.append(
            UAMGroup(name=group_name, users=users, uid=f"gid-{idx}", children=[])
        )
        del k, user_idx, users, idx, group_name
    del group_names

    root = UAM_DB.root
    available = set(range(len(UAM_DB.groups)))
    populate_tree(root, available, 0.1)


def populate_tree(node: UAMGroup, available: set, prob):
    if len(available) == 0:
        return

    cur = {_ for _ in available if random.random() < prob}
    node.children = [UAM_DB.groups[i] for i in cur]
    for i in cur:
        available.remove(i)

    for child in node.children:
        populate_tree(child, available, prob / 2)


def count_users(node: UAMGroup) -> Set[str]:
    users = {_.name for _ in node.users}
    for child in node.children:
        users |= count_users(child)
    return users


def print_tree(node: UAMGroup, prefix=""):
    cnt = len(count_users(node))
    print(f"{prefix}{node.name} ({cnt} users)")
    for child in node.children:
        print_tree(child, prefix + " ")


# ----------------------------------------------------------------------
# Setup Server.
# ----------------------------------------------------------------------
def compile_server_config():
    try:
        cfg = ServerConfig(
            kubeconfig=Path(os.getenv("KUBECONFIG", "")),
            kubecontext=os.getenv("KUBECONTEXT", ""),
            managed_by=os.environ["DFH_MANAGED_BY"],
            env_label=os.environ["DFH_ENV_LABEL"],
            loglevel=os.getenv("DFH_LOGLEVEL", "info"),
            host=os.getenv("DFH_HOST", "0.0.0.0"),
            port=int(os.getenv("DFH_PORT", "5001")),
        )
        return cfg, False
    except (KeyError, ValueError):
        return (
            ServerConfig(
                kubeconfig=Path(""),
                kubecontext="",
                managed_by="",
                env_label="",
                host="",
                port=-1,
                loglevel="",
            ),
            True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_fake_uam_dataset()

    # Create client for one K8s cluster.
    cfg, err = compile_server_config()
    assert not err

    db = Database()
    app.extra.clear()
    app.extra["db"] = db
    app.extra["config"] = cfg

    # Create Database entry for Namespaces and a watcher.
    tasks = []
    for res in db.resources.values():
        k8scfg, err = dfh.watch.create_cluster_config(cfg.kubeconfig, cfg.kubecontext)
        assert not err
        tasks.append(
            asyncio.create_task(dfh.watch.setup_k8s_watch(cfg, k8scfg, db, res))
        )

    logit.info("server startup complete")
    yield

    for task in tasks:
        task.cancel()
        await task
    logit.info("server shutdown complete")


app = FastAPI(
    lifespan=lifespan,
    title="Deployments for Humans",
    summary="",
    description="",
    version="0.1.0",
    db={},
)
app.add_middleware(
    SessionMiddleware,
    secret_key="some-secret",
    max_age=8 * 3600,  # 8 hours
    https_only=False if isLocalDev() else True,
)


# Serve static app.
@app.get("/demo")
async def get_index():
    return FileResponse("static/index.html")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(exc.errors())
    print(exc.body)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )


# ----------------------------------------------------------------------
# Setup Routes.
# ----------------------------------------------------------------------


@app.get("/healthz")
def get_healthz() -> int:
    return status.HTTP_200_OK


@app.get("/api/crt/v1/pods")
def get_pods(request: Request) -> PodList:
    db: Database = request.app.extra["db"]

    ret = PodList()
    for manifest in db.resources["Pod"].manifests.values():
        info, err = dfh.k8s.parse_pod_info(manifest)
        ret.items.append(info) if not err else None
    ret.items.sort(key=lambda _: _.id)

    return ret


@app.get("/api/crt/v1/pods/{name}/{env}")
def get_pods_name_env(name: str, env: str, request: Request) -> PodList:
    db: Database = request.app.extra["db"]

    # Get the pods for the app or return 404 if there is no such app.
    try:
        manifests = db.apps[name][env].resources["Pod"].manifests
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    # Return all the pods of this app.
    ret = PodList()
    for manifest in manifests.values():
        info, err = dfh.k8s.parse_pod_info(manifest)
        ret.items.append(info) if not err else None
    ret.items.sort(key=lambda _: _.id)

    return ret


@app.get("/api/crt/v1/namespaces")
def get_namespaces(request: Request) -> WatchedResource:
    db: Database = request.app.extra["db"]
    return db.resources["Namespace"]


@app.get("/api/crt/v1/apps")
def get_apps(request: Request) -> List[AppEnvOverview]:
    db: Database = request.app.extra["db"]

    # Iterate over our app database in order to find the name of all apps and
    # the environments they are deployed in.
    apps = defaultdict(list)
    for app_name in db.apps:
        for env in db.apps[app_name]:
            apps[app_name].append(env)

    # Convert the apps into a list of `AppOverview` instances that are easy to
    # understand for the frontend.
    resp: List[AppEnvOverview] = []
    for name, envs in dict(apps).items():
        resp.append(AppEnvOverview(id=name, name=name, envs=list(sorted(envs))))

    return resp


@app.get("/api/crt/v1/apps/{name}/{env}")
def get_single_app(name: str, env: str, request: Request) -> AppInfo:
    db: Database = request.app.extra["db"]
    try:
        return db.apps[name][env].appInfo
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )


@app.post("/api/crt/v1/apps/{name}/{env}")
async def post_single_app(name: str, env: str, app_info: AppInfo, request: Request):
    cfg: ServerConfig = request.app.extra["config"]
    db: Database = request.app.extra["db"]

    # Sanity check: meta data in AppInfo must match path parameters.
    if not (app_info.metadata.name == name and app_info.metadata.env == env):
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="AppInfo does not match path parameters.",
        )

    # Sanity check: cannot create an app that already exists.
    try:
        db.apps[name][env]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="App already exists"
        )
    except KeyError:
        pass

    # Create database entry for this app.
    db.apps[name] = db.apps[name] if name in db.apps else {}
    db.apps[name][env] = DatabaseAppEntry(appInfo=app_info)

    # Find all resources that already belong to this app and copy them into the
    # app specific resource DB.
    for kind in db.resources:
        for man_name, manifest in db.resources[kind].manifests.items():
            # Ignore the manifest if it lacks the necessary labels.
            tmp_meta, err = get_metainfo(cfg, manifest)
            if err:
                continue

            # Manifest must belong to the app we are currently creating.
            if not (tmp_meta.name == name and tmp_meta.env == env):
                continue

            # Copy the manifest into the app specific database.
            db.apps[name][env].resources[kind].manifests[man_name] = manifest


async def queue_job(app, jobId: str, sq_plan: DeploymentPlan):
    app.extra["jobs"] = app.extra.get("jobs", {})
    app.extra["jobs"][jobId] = sq_plan


@app.patch("/api/crt/v1/apps/{name}/{env}")
async def patch_single_app(
    name: str, env: str, app_info: AppInfo, request: Request
) -> dfh.square_types.FrontendDeploymentPlan:
    cfg: ServerConfig = request.app.extra["config"]
    db: Database = request.app.extra["db"]

    # Sanity check: meta data in AppInfo must match path parameters.
    if not (app_info.metadata.name == name and app_info.metadata.env == env):
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="AppInfo does not match path parameters.",
        )

    # Sanity check: reject request if the app to patch does not exist.
    try:
        db.apps[name][env].appInfo = app_info
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    sq_plan, err = await dfh.generate.compile_plan(cfg, app_info, db)
    assert not err
    plan = dfh.generate.compile_frontend_plan(sq_plan)

    await queue_job(request.app, plan.jobId, sq_plan)

    return plan


@app.delete("/api/crt/v1/apps/{name}/{env}")
async def delete_single_app(
    name: str, env: str, request: Request
) -> dfh.square_types.FrontendDeploymentPlan:
    db: Database = request.app.extra["db"]
    cfg: ServerConfig = request.app.extra["config"]

    try:
        app_info = db.apps[name][env].appInfo
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    sq_plan, err = await dfh.generate.compile_plan(cfg, app_info, db, remove=True)
    assert not err
    plan = dfh.generate.compile_frontend_plan(sq_plan)

    await queue_job(request.app, plan.jobId, sq_plan)
    db.apps[name].pop(env, None)

    return plan


@app.get("/api/crt/v1/jobs/{jobId}")
def get_jobs(jobId: str) -> JobStatus:
    return JobStatus(jobId=jobId, logs=["line 1", "line 2"], done=True)


@app.post("/api/crt/v1/jobs")
async def post_jobs(job: JobDescription, request: Request):
    cfg: ServerConfig = request.app.extra["config"]
    sq_config = square.dtypes.Config(
        kubeconfig=cfg.kubeconfig,
        kubecontext=cfg.kubecontext,
        folder=Path("/tmp"),
    )

    try:
        plan = request.app.extra["jobs"].pop(job.jobId)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED, detail="Job not found"
        )

    err = await square.apply_plan(sq_config, plan)
    if err:
        raise HTTPException(
            status_code=status.HTTP_418_IM_A_TEAPOT, detail="Job failed"
        )


def is_authenticated(request: Request) -> str:
    email = request.session.get("email")
    if "credentials" not in request.session or email is None:
        raise HTTPException(status_code=403, detail="Not logged in")
    return email


def fetch_user_email(credentials) -> str:
    if isLocalDev():
        htbuild = httplib2.Http(disable_ssl_certificate_validation=True)
    else:
        htbuild = httplib2.Http(disable_ssl_certificate_validation=False)
    client = googleapiclient.discovery.google_auth_httplib2.AuthorizedHttp(
        credentials, http=htbuild
    )
    user_info_service = googleapiclient.discovery.build("oauth2", "v2", http=client)
    user_info = user_info_service.userinfo().get().execute()
    return user_info["email"]


@app.get("/demo/api/test", dependencies=[Depends(is_authenticated)])
def test_api_request(request: Request):
    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **request.session["credentials"]
    )

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    request.session["credentials"] = credentials_to_dict(credentials)
    email = fetch_user_email(credentials)
    return f"User: {email}"


@app.get("/demo/api/login")
def authorize(request: Request):
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )

    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = request.url_for("oauth2callback")

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type="offline",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )

    # Store the state so the callback can verify the auth server response.
    request.session["state"] = state

    return RedirectResponse(url=authorization_url)


@app.post("/demo/api/validate-google-token")
async def google_auth(data: GoogleToken, response: Response):
    try:
        # Verify the ID token using Google's library
        id_info = id_token.verify_oauth2_token(
            data.token, google_requests.Request(), GOOGLE_CLIENT_ID
        )

        # The ID token is valid, you can access user info here:
        user_id = id_info["sub"]  # User's unique ID
        email = id_info["email"]
        name = id_info.get("name", "Anonymous User")

        # Perform user authentication or registration here
        print(f"User was identified as {name} ({email})")
        response.set_cookie(key="email", value=email)
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid ID token")


@app.post("/demo/api/validate-google-token-bearer")
async def google_auth_bearer(data: GoogleToken, response: Response):
    url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={data.token}"
    resp = requests.get(url)
    if resp.status_code == 200:
        id_info = resp.json()
        # The ID token is valid, you can access user info here:
        user_id = id_info["sub"]  # User's unique ID
        email = id_info["email"]
        name = id_info.get("name", "Anonymous User")

        # Perform user authentication or registration here
        print(f"User was identified as {name} ({email})")
        response.set_cookie(key="email", value=email)
    else:
        # Invalid token
        raise HTTPException(status_code=400, detail="Invalid ID token")


@app.get("/demo/api/oauth2callback")
def oauth2callback(request: Request):
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = request.session["state"]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = request.url_for("oauth2callback")

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    resp_url = str(request.url)

    if not isLocalDev():
        resp_url = resp_url.replace("http://", "https://")

    authorization_response = resp_url

    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    request.session["credentials"] = credentials_to_dict(flow.credentials)
    request.session["email"] = fetch_user_email(flow.credentials)

    return RedirectResponse(url=request.url_for("test_api_request"))


@app.get("/demo/api/authdemo")
def authdemo():
    return HTMLResponse(print_index_table())


@app.get("/demo/api/revoke")
def revoke(request: Request):
    if "credentials" not in request.session:
        return HTMLResponse(
            'You need to <a href="/demo/api/authorize">authorize</a> before '
            + "testing the code to revoke credentials."
        )

    credentials = google.oauth2.credentials.Credentials(
        **request.session["credentials"]
    )

    revoke = requests.post(
        "https://oauth2.googleapis.com/revoke",
        params={"token": credentials.token},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    status_code = getattr(revoke, "status_code")
    del request.session["credentials"]
    if status_code == 200:
        return "Credentials successfully revoked."
    else:
        return "An error occurred."


@app.get("/demo/api/clear")
def clear_credentials(request: Request):
    if "credentials" in request.session:
        del request.session["credentials"]
    return "Credentials have been cleared.<br><br>"


@app.get("/authinfo")
def debug_authinfo(request: Request, email: Annotated[dict, Depends(is_authenticated)]):
    return f"Logged in as {email}"


@app.get("/demo/api/groups")
def get_group(request: Request) -> List[UAMGroup]:
    return UAM_DB.groups


@app.get("/demo/api/users")
def get_user(request: Request) -> List[UAMUser]:
    return UAM_DB.users


@app.get("/demo/api/users/{uid}")
def get_users_in_group(
    request: Request, uid: str, recursive: bool = False
) -> List[UAMUser]:
    """Return all users in the group `uid`"""

    users: Dict[str, UAMUser] = {}

    def _walk(node: UAMGroup):
        users.update({_.uid: _ for _ in node.users})
        for child in node.children:
            _walk(child)

    for group in [UAM_DB.root, *UAM_DB.groups]:
        if group.uid == uid:
            if recursive:
                _walk(group)
            else:
                users.update({_.uid: _ for _ in group.users})
            break
    return list(users.values())


@app.get("/demo/api/tree")
def get_tree(request: Request) -> UAMGroup:
    def _walk(node: UAMGroup) -> UAMGroup:
        out = UAMGroup(uid=node.uid, name=node.name, users=[], children=[])
        for child in node.children:
            out.children.append(_walk(child))
        return out

    return _walk(UAM_DB.root)


@app.get("/demo/api/simulate-login")
def simulate_login(request: Request, response: Response):
    email = "foo@bar.com"
    response.set_cookie(key="email", value=email)
    return {"email": email}


@app.get("/demo/api/simulate-logout")
def simulate_logout(request: Request, response: Response):
    response.delete_cookie(key="email")
    return {"email": ""}


# Serve static web app on all paths that have not been defined already.
@app.get("/{path:path}")
async def catch_all(path: str):
    return FileResponse("static/index.html")


def credentials_to_dict(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def print_index_table():
    return (
        "<table>"
        + '<tr><td><a href="/demo/api/test">Test an API request</a></td>'
        + "<td>Submit an API request and see a formatted JSON response. "
        + "    Go through the authorization flow if there are no stored "
        + "    credentials for the user.</td></tr>"
        + '<tr><td><a href="/demo/api/authorize">Test the auth flow directly</a></td>'
        + "<td>Go directly to the authorization flow. If there are stored "
        + "    credentials, you still might not be prompted to reauthorize "
        + "    the application.</td></tr>"
        + '<tr><td><a href="/demo/api/revoke">Revoke current credentials</a></td>'
        + "<td>Revoke the access token associated with the current user "
        + "    session. After revoking credentials, if you go to the test "
        + "    page, you should see an <code>invalid_grant</code> error."
        + "</td></tr>"
        + '<tr><td><a href="/demo/api/clear">Clear session credentials</a></td>'
        + "<td>Clear the access token currently stored in the user session. "
        + '    After clearing the token, if you <a href="/demo/api/test">test the '
        + "    API request</a> again, you should go back to the auth flow."
        + "</td></tr>"
        + '<tr><td><a href="/demo/api/authinfo">Debug Session Info</a></td></tr>'
        + "</table>"
    )
