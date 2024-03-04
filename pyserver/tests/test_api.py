import asyncio
import time
from pathlib import Path
from typing import List
from unittest import mock

import pytest
import square.dtypes
from fastapi.testclient import TestClient

import dfh.api
import dfh.defaults
import dfh.generate
import dfh.k8s
import dfh.watch
import tests.test_helpers as test_helpers
from dfh.models import (
    AppCanary,
    AppEnvOverview,
    AppInfo,
    AppMetadata,
    AppPrimary,
    AppService,
    Database,
    DeploymentInfo,
    JobDescription,
    JobStatus,
    K8sEnvVar,
    PodList,
    ServerConfig,
    WatchedResource,
)
from dfh.square_types import FrontendDeploymentPlan

from .conftest import K8sConfig, get_server_config
from .test_helpers import create_temporary_k8s_namespace, deploy_test_app

cfg = get_server_config()


class TestBasic:
    def test_compile_server_config(self):
        # Minimum required environment variables.
        # NOTE: it is avlid to not specify a Kubeconfig file, most notably when
        # running inside a Pod.
        new_env = {
            "DFH_MANAGED_BY": "foo",
            "DFH_ENV_LABEL": "bar",
        }
        with mock.patch.dict("os.environ", values=new_env, clear=True):
            cfg, err = dfh.api.compile_server_config()
            assert not err
            assert cfg == ServerConfig(
                kubeconfig=Path(""),
                kubecontext="",
                managed_by="foo",
                env_label="bar",
                host="0.0.0.0",
                port=5001,
                loglevel="info",
            )

        # Explicit values for everything.
        new_env = {
            "KUBECONFIG": "/tmp/kind-kubeconf.yaml",
            "KUBECONTEXT": "kind-kind",
            "DFH_MANAGED_BY": "foo",
            "DFH_ENV_LABEL": "bar",
            "DFH_LOGLEVEL": "error",
            "DFH_HOST": "1.2.3.4",
            "DFH_PORT": "1234",
        }
        with mock.patch.dict("os.environ", values=new_env, clear=True):
            cfg, err = dfh.api.compile_server_config()
            assert not err
            assert cfg == ServerConfig(
                kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
                kubecontext="kind-kind",
                managed_by="foo",
                env_label="bar",
                host="1.2.3.4",
                port=1234,
                loglevel="error",
            )

        # Invalid because DFH_MANAGED_BY and DFH_ENV_LABEL are both mandatory.
        with mock.patch.dict("os.environ", values={}, clear=True):
            cfg, err = dfh.api.compile_server_config()
            assert err

        # Must have correctly received the values from the `.env` file.
        cfg, err = dfh.api.compile_server_config()
        assert not err
        assert cfg == ServerConfig(
            kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
            kubecontext="kind-kind",
            managed_by="dfh",
            env_label="env",
            host="0.0.0.0",
            port=5001,
            loglevel="info",
        )


class TestAPI:
    def test_get_root(self, client):
        # Must serve the webapp on all routes by default.
        for path in ("/", "/static/index.html", "/anywhere/but/api"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.text == "Placeholder static/index.html"

        # Assets are also used by static web apps.
        response = client.get("/assets/index.html")
        assert response.status_code == 200
        assert response.text == "Placeholder assets/index.html"

    def test_get_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200

    @mock.patch.object(dfh.generate, "compile_plan")
    def test_crud_apps(self, m_plan, client: TestClient):
        # Mock plan.
        m_plan.return_value = (
            FrontendDeploymentPlan(jobId="foo", create=[], patch=[], delete=[]),
            False,
        )

        # Fixtures.
        name, namespace, env = "foo", "nsfoo", "stg"
        path = f"/api/crt/v1/apps/{name}/{env}"
        info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=namespace),
        )

        # Must return an empty list of apps.
        response = client.get("/api/crt/v1/apps")
        assert response.status_code == 200
        overview = [AppEnvOverview.model_validate(_) for _ in response.json()]
        assert overview == []
        del overview

        # ----------------------------------------------------------------------
        # Gracefully handle non-existing apps.
        # ----------------------------------------------------------------------
        response = client.get(path)
        assert response.status_code == 404

        response = client.patch(path, json=info.model_dump())
        assert response.status_code == 404

        response = client.delete(path)
        assert response.status_code == 404

        # ----------------------------------------------------------------------
        # Create an app and verify that we cannot create twice.
        # ----------------------------------------------------------------------
        info.primary.deployment.image = "image:v1"
        response = client.post(path, json=info.model_dump())
        assert response.status_code == 200

        response = client.get(path)
        assert response.status_code == 200
        ret = AppInfo.model_validate(response.json())
        assert ret == info and ret.primary.deployment.image == "image:v1"

        # Must not allow to create the same app twice.
        info.primary.deployment.image = "image:v2"
        response = client.post(path, json=info.model_dump())
        assert response.status_code == 409

        # Must not have updated the existing app.
        response = client.get(path)
        assert response.status_code == 200
        ret = AppInfo.model_validate(response.json())
        assert ret.primary.deployment.image == "image:v1"

        # `/api/crt/v1/apps` endpoint must return all apps.
        response = client.get("/api/crt/v1/apps")
        assert response.status_code == 200
        overview = [AppEnvOverview.model_validate(_) for _ in response.json()]
        assert (
            len(overview) == 1
            and overview[0].envs == [env]
            and overview[0].name == name
        )
        del overview

        # ----------------------------------------------------------------------
        # Patch the app.
        # ----------------------------------------------------------------------
        info.primary.deployment.image = "image:v3"
        response = client.patch(path, json=info.model_dump())
        assert response.status_code == 200

        response = client.get(path)
        assert response.status_code == 200
        ret = AppInfo.model_validate(response.json())
        assert ret == info and ret.primary.deployment.image == "image:v3"

        # ----------------------------------------------------------------------
        # Delete the app and verify that we can only do it once.
        # ----------------------------------------------------------------------
        response = client.delete(path)
        assert response.status_code == 200

        response = client.delete(path)
        assert response.status_code == 404

    @pytest.mark.parametrize("name", ["foo", "bar"])
    @pytest.mark.parametrize("env", ["stg", "prod"])
    def test_get_app(self, env: str, name: str, client: TestClient):
        test_helpers.add_app(client, name, "ns", env)

        response = client.get(f"/api/crt/v1/apps/{name}/{env}")
        assert response.status_code == 200

        data = AppInfo.model_validate(response.json())
        assert data.metadata.name == name
        assert data.metadata.env == env

    @mock.patch.object(dfh.generate, "compile_plan")
    def test_post_app_sane_payload(self, m_plan, client: TestClient):
        # Mock plan.
        m_plan.return_value = (
            FrontendDeploymentPlan(jobId="foo", create=[], patch=[], delete=[]),
            False,
        )

        # Fixtures.
        name, namespace, env = "demo", "default", "stg"
        url = f"/api/crt/v1/apps/{name}/{env}"

        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=namespace),
        )

        # Reject `app_info` if its `name` and `env` attributes do not match the
        # path parameters.
        app_info.metadata.name = "not-demo"
        response = client.post(url, json=app_info.model_dump())
        assert response.status_code == 406

        # Must accept valid app.
        app_info.metadata.name = "demo"
        response = client.post(url, json=app_info.model_dump())
        assert response.status_code == 200

    @mock.patch.object(dfh.generate, "compile_plan")
    def test_post_app_import_existing(self, m_plan, client: TestClient):
        """Create an app for which some resources already exists.

        This typically happens when we want to import an app into DFH that was
        already deployed.

        """
        # Mock plan.
        m_plan.return_value = (
            FrontendDeploymentPlan(jobId="foo", create=[], patch=[], delete=[]),
            False,
        )

        # Fixtures.
        name, ns, env = "demo", "default", "stg"
        db: Database = client.app.extra["db"]  # type: ignore
        url = f"/api/crt/v1/apps/{name}/{env}"

        # Insert a DFH deployment with 2 pods as well as an unrelated pod.
        app_info = test_helpers.add_app(client, name, ns, env, num_pods=2)
        db.resources["Pod"].manifests["foo/bar-foobar"] = {
            "metadata": {"name": "foo", "namespace": "blah"},
        }

        assert len(db.apps) == 1
        assert len(db.apps[name][env].resources["Deployment"].manifests) == 1
        assert len(db.apps[name][env].resources["Pod"].manifests) == 2
        assert len(db.resources["Deployment"].manifests) == 1
        assert len(db.resources["Pod"].manifests) == 3

        # Manually remove the app from our DB but keep the resources.
        del db.apps[name]

        # DFH must not know about the app anymore.
        resp = client.get(url)
        assert resp.status_code == 404

        # Import the app into DFH.
        app_info.metadata.name = "demo"
        response = client.post(url, json=app_info.model_dump())
        assert response.status_code == 200

        # Must have found the resources again.
        assert len(db.apps) == 1
        assert len(db.apps[name]) == 1
        assert len(db.apps[name][env].resources["Deployment"].manifests) == 1
        assert len(db.apps[name][env].resources["Pod"].manifests) == 2
        assert len(db.resources["Deployment"].manifests) == 1
        assert len(db.resources["Pod"].manifests) == 3

    @mock.patch.object(dfh.generate, "compile_plan")
    def test_patch_app(self, m_plan, client: TestClient):
        # Mock plan.
        m_plan.return_value = (
            FrontendDeploymentPlan(jobId="foo", create=[], patch=[], delete=[]),
            False,
        )

        # Install app.
        name, namespace, env = "demo", "default", "stg"
        app_info = test_helpers.add_app(client, name, namespace, env)
        url = f"/api/crt/v1/apps/{name}/{env}"

        # Must accept valid patch.
        response = client.patch(url, json=app_info.model_dump())
        assert response.status_code == 200

        # Reject invalid payload.
        response = client.patch(url, json={"not a": "DeploymentInfo"})
        assert response.status_code == 422

        # Reject `app_info` if its `name` and `env` attributes do not match the
        # path parameters.
        app_info.metadata.name += "foo"
        response = client.patch(url, json=app_info.model_dump())
        assert response.status_code == 406

    def test_get_apps(self, client: TestClient):
        response = client.get(f"/api/crt/v1/apps")
        assert response.status_code == 200
        assert len(response.json()) == 0

        app_1 = AppInfo(
            metadata=AppMetadata(name="app-1", env="stg", namespace="default"),
        )
        app_2 = AppInfo(
            metadata=AppMetadata(name="app-2", env="prod", namespace="default"),
        )

        # Install the DB that the lifespan handler would otherwise create.
        db = Database()
        client.app.extra["db"] = db  # type: ignore

        # Pretend the watch reported two Deployments.
        response = client.post(f"/api/crt/v1/apps/app-1/stg", json=app_1.model_dump())
        assert response.status_code == 200
        response = client.post(f"/api/crt/v1/apps/app-2/prod", json=app_2.model_dump())
        assert response.status_code == 200

        response = client.get("/api/crt/v1/apps")
        assert response.status_code == 200
        assert len(response.json()) == 2

        apps = [AppEnvOverview.model_validate(_) for _ in response.json()]
        assert len(apps) == 2
        assert {_.name for _ in apps} == {"app-1", "app-2"}
        assert {tuple(_.envs) for _ in apps} == {("prod",), ("stg",)}

    def test_get_pods_all_envs(self, client: TestClient):
        # Must not return any pods.
        ret = client.get(f"/api/crt/v1/pods")
        assert ret.status_code == 200
        resp = PodList.model_validate(ret.json())
        assert len(resp.items) == 0

        # Insert a deployment with 2 pods.
        test_helpers.add_app(client, "demo", "default", "stg", num_pods=2)

        # API must now provide two pods.
        ret = client.get(f"/api/crt/v1/pods")
        assert ret.status_code == 200
        resp = PodList.model_validate(ret.json())
        assert len(resp.items) == 2

        # Item IDs (for frontend) must be based on name and namespace of Pod.
        assert resp.items[0].id == "default/demo-1234-0"
        assert resp.items[1].id == "default/demo-1234-1"
        assert resp.items[0].name == "demo-1234-0"
        assert resp.items[1].name == "demo-1234-1"

    def test_get_pods_specific_name_and_env(self, client: TestClient):
        # Must not return any pods.
        ret = client.get(f"/api/crt/v1/pods/demo1/stg")
        assert ret.status_code == 404

        # Insert a deployment with 2 pods.
        test_helpers.add_app(client, "demo1", "ns-stg", "stg", num_pods=2)
        test_helpers.add_app(client, "demo1", "ns-prod", "prod", num_pods=2)
        test_helpers.add_app(client, "demo2", "ns-stg", "stg", num_pods=2)
        test_helpers.add_app(client, "demo2", "ns-prod", "prod", num_pods=2)

        # Base API must provide eight pods.
        ret = client.get(f"/api/crt/v1/pods")
        assert ret.status_code == 200
        resp = PodList.model_validate(ret.json())
        assert len(resp.items) == 8

        # Query specific pods.
        for name in ("demo1", "demo2"):
            for env in ("stg", "prod"):
                ret = client.get(f"/api/crt/v1/pods/{name}/{env}")
                assert ret.status_code == 200
                resp = PodList.model_validate(ret.json())
                assert len(resp.items) == 2

                # Item IDs (for frontend) must be based on name and namespace of Pod.
                assert resp.items[0].id == f"ns-{env}/{name}-1234-0"
                assert resp.items[1].id == f"ns-{env}/{name}-1234-1"
                assert resp.items[0].name == f"{name}-1234-0"
                assert resp.items[1].name == f"{name}-1234-1"

    def test_get_jobs(self, client: TestClient):
        ret = client.get(f"/api/crt/v1/jobs/123")
        assert ret.status_code == 200

    @mock.patch.object(dfh.api.square, "apply_plan")
    async def test_post_jobs(self, m_plan, client: TestClient):
        m_plan.return_value = False
        job = JobDescription(jobId="jobid")
        plan = square.dtypes.DeploymentPlan(create=[], patch=[], delete=[])

        # Queue a fake job.
        await dfh.api.queue_job(client.app, job.jobId, plan)

        # Must return 200 because the job exists.
        ret = client.post(f"/api/crt/v1/jobs", json=job.model_dump())
        assert ret.status_code == 200

        # Must return 412 because the job does not exist anymore.
        job = JobDescription(jobId="jobid")
        ret = client.post(f"/api/crt/v1/jobs", json=job.model_dump())
        assert ret.status_code == 412

        # Must return 418 because the job failed.
        await dfh.api.queue_job(client.app, job.jobId, plan)
        m_plan.return_value = True
        job = JobDescription(jobId="jobid")
        ret = client.post(f"/api/crt/v1/jobs", json=job.model_dump())
        assert ret.status_code == 418


class TestIntegration:
    async def test_namespaces_from_k8s(self, realK8sCfg: K8sConfig, client: TestClient):
        async with deploy_test_app(client) as (namespace, _, _):
            _, err = await dfh.k8s.get(realK8sCfg, f"/api/v1/namespaces/{namespace}")
            assert not err

    def test_get_namespaces(self, clientls: TestClient):
        """Serves as a simple integration test to ensure the namespace watch works."""
        for _ in range(10):
            time.sleep(0.1)
            response = clientls.get("/api/crt/v1/namespaces")
            assert response.status_code == 200

            res = WatchedResource.model_validate(response.json())
            if "/default" in res.manifests:
                break
        else:
            assert False

    async def test_create_app(self, clientls: TestClient, realK8sCfg: K8sConfig):
        """Create an entire app from scratch."""
        client = clientls

        name, env = "demo", "sit"

        async with create_temporary_k8s_namespace(client) as namespace:
            # --- There must be no apps yet. ---
            ret = client.get("/api/crt/v1/apps")
            assert ret.status_code == 200 and len(ret.json()) == 0

            # --- Define an app and request a plan from the jobs endpoint ---
            app_info = AppInfo(
                metadata=AppMetadata(name=name, env=env, namespace=namespace),
                primary=AppPrimary(
                    deployment=DeploymentInfo(
                        isFlux=False,
                        name="main",
                        image="nginx:1.11",
                        envVars=[K8sEnvVar(name="create", value="app")],
                    ),
                    useService=True,
                    service=AppService(port=90, targetPort=9090),
                ),
            )

            # Insert the App.
            ret = client.post(
                f"/api/crt/v1/apps/{name}/{env}", json=app_info.model_dump()
            )
            assert ret.status_code == 200

            # Request a plan based on the supplied AppInfo.
            ret = client.patch(
                f"/api/crt/v1/apps/{name}/{env}", json=app_info.model_dump()
            )
            assert ret.status_code == 200

            plan = FrontendDeploymentPlan.model_validate(ret.json())
            assert len(plan.create) == 2
            assert plan.jobId != ""

            # --- Request to implement the plan ---
            jd = JobDescription(jobId=plan.jobId)
            ret = client.post(f"/api/crt/v1/jobs", json=jd.model_dump())
            assert ret.status_code == 200

            for _ in range(10):
                time.sleep(0.5)

                ret = client.get(f"/api/crt/v1/jobs/{plan.jobId}")
                assert ret.status_code == 200
                job = JobStatus.model_validate(ret.json())
                if job.done:
                    break
            else:
                assert False, "job did not complete"

            # --- Query K8s to get the information from the horse's mouth ---
            # Deployment.
            resp, err = await dfh.k8s.get(
                realK8sCfg,
                f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
            )
            assert not err
            env_vars = resp["spec"]["template"]["spec"]["containers"][0]["env"]
            default_envs = [
                _.model_dump(exclude_defaults=True)
                for _ in dfh.defaults.pod_fieldref_envs()
            ]
            assert env_vars == [{"name": "create", "value": "app"}] + default_envs

            # Service.
            resp, err = await dfh.k8s.get(
                realK8sCfg,
                f"/api/v1/namespaces/{namespace}/services/{name}",
            )
            assert not err
            env_vars = resp["spec"]["ports"][0]["port"] = 90
            env_vars = resp["spec"]["ports"][0]["targetPort"] = 90900

    async def test_get_patch(self, clientls: TestClient, realK8sCfg: K8sConfig):
        client = clientls

        async with deploy_test_app(client) as (namespace, name, envs):
            assert len(envs) == 1
            env = envs[0]

            # --- Get all apps in all envs and verify that our test app is among them. ---
            await asyncio.sleep(1)

            ret = client.get("/api/crt/v1/apps")
            assert ret.status_code == 200

            # There must be exactly one app deployed.
            # todo: can I compare Pydantic models here?
            data: List[AppEnvOverview] = [
                AppEnvOverview.model_validate(_) for _ in ret.json()
            ]
            assert len(data) == 1
            del data

            # --- get all configurable items for the app ---
            ret = client.get(f"/api/crt/v1/apps/{name}/{env}")
            assert ret.status_code == 200
            app = AppInfo.model_validate(ret.json())
            app.metadata.namespace = namespace

            assert app.primary.deployment.image != ""

            # --- Modify the app and request a plan from the jobs endpoint ---
            assert app.primary.deployment
            assert len(app.primary.deployment.envVars) == 0
            app.primary.deployment.envVars.append(K8sEnvVar(name="foo", value="bar"))

            ret = client.patch(f"/api/crt/v1/apps/{name}/{env}", json=app.model_dump())
            assert ret.status_code == 200
            plan = FrontendDeploymentPlan.model_validate(ret.json())
            assert plan.jobId != ""

            # --- Request to implement the plan ---
            jd = JobDescription(jobId=plan.jobId)
            ret = client.post(f"/api/crt/v1/jobs", json=jd.model_dump())
            assert ret.status_code == 200

            for _ in range(10):
                time.sleep(0.5)

                ret = client.get(f"/api/crt/v1/jobs/{plan.jobId}")
                assert ret.status_code == 200
                job = JobStatus.model_validate(ret.json())
                if job.done:
                    break
            else:
                assert False, "job did not complete"

            # --- Query our app to see if it has tracked the changes ---
            await asyncio.sleep(1)
            ret = client.get(f"/api/crt/v1/apps/{name}/{env}")
            assert ret.status_code == 200
            app = AppInfo.model_validate(ret.json())
            assert app.primary.deployment
            assert app.primary.deployment.envVars == [
                K8sEnvVar(name="foo", value="bar")
            ]

            # --- Query K8s to get the information from the horse's mouth ---
            resp, err = await dfh.k8s.get(
                realK8sCfg,
                f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
            )
            assert not err

            env_vars = resp["spec"]["template"]["spec"]["containers"][0]["env"]
            default_envs = [
                _.model_dump(exclude_defaults=True)
                for _ in dfh.defaults.pod_fieldref_envs()
            ]
            assert env_vars == [{"name": "foo", "value": "bar"}] + default_envs


class TestIntegrationCanary:
    async def test_canary(self, clientls: TestClient, realK8sCfg: K8sConfig):
        client, k8sCfg = clientls, realK8sCfg
        del clientls, realK8sCfg

        async with deploy_test_app(client) as (namespace, name, envs):
            assert len(envs) == 1
            env = envs[0]

            # --- Get all apps in all envs and verify that our test app is among them. ---
            await asyncio.sleep(1)

            ret = client.get("/api/crt/v1/apps")
            assert ret.status_code == 200

            # There must be exactly one app deployed.
            # todo: can I compare Pydantic models here?
            data: List[AppEnvOverview] = [
                AppEnvOverview.model_validate(_) for _ in ret.json()
            ]
            data: List[AppEnvOverview] = [
                _ for _ in data if _.name == name and _.envs == envs
            ]
            assert len(data) == 1
            del data

            # --- get all configurable items for the app ---
            ret = client.get(f"/api/crt/v1/apps/{name}/{env}")
            assert ret.status_code == 200
            app = AppInfo.model_validate(ret.json())
            assert app.primary.deployment
            app.metadata.namespace = namespace

            # --- Modify the app: to duplicate the primary app as a canary ---
            app.hasCanary = True
            app.canary = AppCanary.model_validate(app.primary.model_dump())
            app.canary.deployment.image = "nginx:1.20"

            ret = client.patch(f"/api/crt/v1/apps/{name}/{env}", json=app.model_dump())
            assert ret.status_code == 200
            plan = FrontendDeploymentPlan.model_validate(ret.json())
            assert plan.jobId != ""

            # Must create one Deployment, VirtualService and DestinationRule.
            assert len(plan.create) == 3

            # --- Tell server to implement the plan ---
            jd = JobDescription(jobId=plan.jobId)
            ret = client.post(f"/api/crt/v1/jobs", json=jd.model_dump())
            assert ret.status_code == 200

            for _ in range(10):
                time.sleep(0.5)

                ret = client.get(f"/api/crt/v1/jobs/{plan.jobId}")
                assert ret.status_code == 200
                job = JobStatus.model_validate(ret.json())
                if job.done:
                    break
            else:
                assert False, "job did not complete"

            # --- Query our app to see if it has tracked the changes ---
            await asyncio.sleep(1)
            ret = client.get(f"/api/crt/v1/apps/{name}/{env}")
            assert ret.status_code == 200
            app = AppInfo.model_validate(ret.json())
            assert app.primary.deployment
            assert app.hasCanary is True
            assert app.canary.deployment

            # --- Query K8s to get the information from the horse's mouth ---
            url = f"/apis/apps/v1/namespaces/{namespace}/deployments"
            resp, err = await dfh.k8s.get(k8sCfg, f"{url}/{name}")
            assert not err
            assert resp["metadata"]["labels"].get("deployment-type", "") == "primary"

            resp, err = await dfh.k8s.get(k8sCfg, f"{url}/{name}-canary")
            assert not err
            assert resp["metadata"]["labels"].get("deployment-type", "") == "canary"

            url = f"/apis/networking.istio.io/v1beta1/namespaces/{namespace}"
            resp, err = await dfh.k8s.get(k8sCfg, f"{url}/virtualservices/{name}")
            assert not err
            assert resp["metadata"]["labels"].get("deployment-type", "") == "primary"

            resp, err = await dfh.k8s.get(k8sCfg, f"{url}/destinationrules/{name}")
            assert not err
            assert resp["metadata"]["labels"].get("deployment-type", "") == "primary"
