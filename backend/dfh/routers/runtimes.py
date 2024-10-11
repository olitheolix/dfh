from collections import defaultdict
from pathlib import Path
from typing import List

import square.dtypes
import square.k8s
from fastapi import APIRouter, HTTPException, Request, status
from square.square import DeploymentPlan

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
    JobDescription,
    JobStatus,
    PodList,
    ServerConfig,
    WatchedResource,
)

router = APIRouter()


@router.get("/v1/pods")
def get_pods(request: Request) -> PodList:
    db: Database = request.app.extra["db"]

    ret = PodList()
    for manifest in db.resources["Pod"].manifests.values():
        info, err = dfh.k8s.parse_pod_info(manifest)
        ret.items.append(info) if not err else None
    ret.items.sort(key=lambda _: _.id)

    return ret


@router.get("/v1/pods/{name}/{env}")
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


@router.get("/v1/namespaces")
def get_namespaces(request: Request) -> WatchedResource:
    db: Database = request.app.extra["db"]
    return db.resources["Namespace"]


@router.get("/v1/apps")
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


@router.get("/v1/apps/{name}/{env}")
def get_single_app(name: str, env: str, request: Request) -> AppInfo:
    db: Database = request.app.extra["db"]
    try:
        return db.apps[name][env].appInfo
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )


@router.post("/v1/apps/{name}/{env}")
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


@router.patch("/v1/apps/{name}/{env}")
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


@router.delete("/v1/apps/{name}/{env}")
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


@router.get("/v1/jobs/{jobId}")
def get_jobs(jobId: str) -> JobStatus:
    return JobStatus(jobId=jobId, logs=["line 1", "line 2"], done=True)


@router.post("/v1/jobs")
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
