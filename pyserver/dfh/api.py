import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import square.dtypes
import square.k8s
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
    JobDescription,
    JobStatus,
    PodList,
    ServerConfig,
    WatchedResource,
)

# Convenience.
logit = logging.getLogger("app")


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
        )
        return cfg, False
    except KeyError:
        return (
            ServerConfig(
                kubeconfig=Path(""), kubecontext="", managed_by="", env_label=""
            ),
            True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


# Serve static app.
@app.get("/")
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


@app.patch("/api/crt/v1/apps/{name}/{env}")
async def patch_single_app(
    name: str, env: str, app_info: AppInfo, request: Request
) -> dfh.square_types.DeploymentPlan:
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

    request.app.extra["jobs"] = request.app.extra.get("jobs", {})
    request.app.extra["jobs"][plan.jobId] = sq_plan

    return plan


@app.delete("/api/crt/v1/apps/{name}/{env}")
async def delete_single_app(
    name: str, env: str, request: Request
) -> dfh.square_types.DeploymentPlan:
    db: Database = request.app.extra["db"]

    # FIXME: how to delete with Square?
    sq_plan = square.dtypes.DeploymentPlan(create=[], patch=[], delete=[])
    plan = dfh.generate.compile_frontend_plan(sq_plan)

    try:
        del db.apps[name][env]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    request.app.extra["jobs"] = request.app.extra.get("jobs", {})
    request.app.extra["jobs"][plan.jobId] = sq_plan

    return plan


@app.get("/api/crt/v1/jobs/{jobId}")
def get_jobs(jobId: str) -> JobStatus:
    import faker

    return JobStatus(
        jobId=jobId, logs=[faker.Faker().name(), faker.Faker().name()], done=True
    )


@app.post("/api/crt/v1/jobs")
async def post_jobs(job: JobDescription, request: Request):
    cfg: ServerConfig = request.app.extra["config"]
    sq_config = square.dtypes.Config(
        kubeconfig=cfg.kubeconfig,
        kubecontext=cfg.kubecontext,
        # Store manifests in this folder.
        folder=Path("/tmp"),
    )

    plan = request.app.extra["jobs"][job.jobId]
    err = await square.apply_plan(sq_config, plan)
    assert not err


# Serve static web app on all paths that have not been defined already.
@app.get("/{path:path}")
async def catch_all(path: str, request: Request):
    return FileResponse("static/index.html")
