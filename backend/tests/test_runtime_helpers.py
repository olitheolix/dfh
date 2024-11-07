import random
import copy
import time
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

import dfh.generate
import dfh.k8s
import dfh.watch
from dfh.models import (
    AppInfo,
    AppMetadata,
    AppPrimary,
    Database,
    K8sProbe,
    K8sProbeHttp,
    K8sResourceCpuMem,
)

from .conftest import get_server_config


@asynccontextmanager
async def create_temporary_k8s_namespace(client: TestClient):
    cfg = get_server_config()
    k8scfg, err = dfh.watch.create_cluster_config(cfg.kubeconfig, cfg.kubecontext)
    assert not err

    ts = int(1000 * time.time())
    namespace = f"test-{ts}"

    ns_manifest = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "labels": {
                "istio-injection": "enabled",
                "kubernetes.io/metadata.name": "default",
            },
            "name": namespace,
        },
    }

    del_opts = {
        "apiVersion": "v1",
        "kind": "DeleteOptions",
        "gracePeriodSeconds": 0,
        "orphanDependents": False,
    }

    # Create the Namespace and primary/canary Deployments.
    try:
        _, err = await dfh.k8s.post(k8scfg, "/api/v1/namespaces", ns_manifest)
        assert not err
        yield namespace
    finally:
        _, _ = await dfh.k8s.delete(k8scfg, f"/api/v1/namespaces/{namespace}", del_opts)


@asynccontextmanager
async def deploy_test_app(client: TestClient):
    cfg = get_server_config()
    k8scfg, err = dfh.watch.create_cluster_config(cfg.kubeconfig, cfg.kubecontext)
    assert not err

    name, env = f"app-{random.randint(1000, 9999)}", "stg"

    async with create_temporary_k8s_namespace(client) as namespace:
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=namespace),
            primary=AppPrimary(
                deployment=dfh.generate.DeploymentInfo(
                    isFlux=False,
                    resources=dfh.generate.K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="100M"),
                        limits=K8sResourceCpuMem(memory="200M"),
                    ),
                    useResources=True,
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                    useLivenessProbe=True,
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                    useReadinessProbe=True,
                    image="nginx:1.25",
                    name="main",
                )
            ),
        )

        # Upload app definition to dfh.
        response = client.post(f"/v1/apps/{name}/{env}", json=app_info.model_dump())
        assert response.status_code == 200

        data, err = dfh.generate.manifests_from_appinfo(cfg, app_info, Database())
        assert not err

        # Create the Namespace and primary/canary Deployments.
        try:
            for manifest in data.resources["Deployment"].manifests.values():
                _, err = await dfh.k8s.post(
                    k8scfg,
                    f"/apis/apps/v1/namespaces/{namespace}/deployments",
                    manifest,
                )
                assert not err

            yield namespace, name, [env]
        finally:
            pass


def add_app(
    client: TestClient,
    name: str,
    namespace: str,
    env: str,
    deployment: bool = True,
    canary: bool = False,
    num_pods: int = 0,
) -> AppInfo:
    # Convenience.
    cfg = get_server_config()
    db = client.app.extra["db"]  # type: ignore

    app_info = AppInfo(
        metadata=AppMetadata(name=name, env=env, namespace=namespace),
        primary=AppPrimary(
            deployment=dfh.generate.DeploymentInfo(
                isFlux=False,
                resources=dfh.generate.K8sRequestLimit(
                    requests=K8sResourceCpuMem(cpu="100m", memory="100M"),
                    limits=K8sResourceCpuMem(memory="200M"),
                ),
                useResources=True,
                livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                useLivenessProbe=True,
                readinessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/ready", port=80)),
                useReadinessProbe=True,
                envVars=[dfh.generate.K8sEnvVar(name="key", value="value")],
                image="nginx:1.25",
                name="main",
            )
        ),
    )

    # Upload app definition to dfh.
    response = client.post(f"/v1/apps/{name}/{env}", json=app_info.model_dump())
    assert response.status_code == 200

    if deployment:
        data, err = dfh.generate.manifests_from_appinfo(cfg, app_info, db)
        assert not err

        for manifest in data.resources["Deployment"].manifests.values():
            assert not dfh.watch.track_resource(
                cfg,
                db,
                db.resources["Deployment"],
                {"type": "ADDED", "object": manifest},
            )

            for i in range(num_pods):
                pod = copy.deepcopy(manifest["spec"]["template"])
                pod["apiVersion"] = "v1"
                pod["kind"] = "Pod"
                pod["metadata"]["name"] = manifest["metadata"]["name"] + f"-1234-{i}"
                pod["metadata"]["namespace"] = manifest["metadata"]["namespace"]
                assert not dfh.watch.track_resource(
                    cfg, db, db.resources["Pod"], {"type": "ADDED", "object": pod}
                )
    return app_info
