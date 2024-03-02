from pathlib import Path
from typing import Dict

import pytest

import dfh.api
import dfh.generate as gen
import dfh.watch
from dfh.manifest_utilities import is_dfh_manifest
from dfh.models import (
    AppCanary,
    AppInfo,
    AppMetadata,
    AppPrimary,
    AppService,
    Database,
    DatabaseAppEntry,
    DeploymentInfo,
    K8sEnvVar,
    K8sProbe,
    K8sProbeHttp,
    K8sRequestLimit,
    K8sResourceCpuMem,
    K8sService,
    KeyValue,
    ServerConfig,
    WatchedResource,
)

# Convenience: we can re-use it in all tests.
from .conftest import get_server_config

cfg = get_server_config()


def convert_manifest(manifest: dict) -> Dict[str, WatchedResource]:
    key, kind, err = dfh.watch.get_resource_key(manifest)
    assert not err

    # Copy the manifest into a Dict[str, WatchedResource] format for `info_from_manifests`.
    watched_res = WatchedResource(apiVersion="apps/v1", kind="Deployment", path="")
    watched_res.manifests[key] = manifest
    k8s_res = {kind: watched_res}
    return k8s_res


class TestBasic:
    def test_resource_labels(self):
        name, ns, env = "demo", "default", "stg"
        meta = AppMetadata(name=name, env=env, namespace=ns)
        primary_labels = gen.resource_labels(cfg, meta, False)
        canary_labels = gen.resource_labels(cfg, meta, True)

        # Canary must have the same labels as primary plus a `type` label.
        assert primary_labels.pop("deployment-type") == "primary"
        assert canary_labels.pop("deployment-type") == "canary"
        assert primary_labels == canary_labels

        assert primary_labels == {
            "app": meta.name,
            cfg.env_label: meta.env,
            "app.kubernetes.io/name": meta.name,
            "app.kubernetes.io/managed-by": cfg.managed_by,
        }

    def test_info_from_manifests_empty(self):
        out_info, err = gen.appinfo_from_manifests(
            cfg,
            {
                "Deployment": WatchedResource(
                    apiVersion="apps/v1", kind="Deployment", path=""
                )
            },
        )
        assert not err
        assert AppInfo() == out_info

    def test_info_from_manifests_invalid_structure(self):
        name, ns, env = "demo", "default", "stg"

        # Must accept minimal specimen.
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
        )
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        _, err = gen.appinfo_from_manifests(cfg, convert_manifest(manifest))
        assert not err

        res = WatchedResource(apiVersion="apps/v1", kind="Deployment", path="")

        # Must reject manifest with wrong resource version.
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        manifest["apiVersion"] = "foo"
        res.manifests["some-name"] = manifest
        _, err = gen.appinfo_from_manifests(cfg, {"Deployment": res})
        assert err

        # Must reject manifest with wrong resource kind.
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        manifest["kind"] = "foo"
        res.manifests["some-name"] = manifest
        _, err = gen.appinfo_from_manifests(cfg, {"Deployment": res})
        assert err

        # Must reject manifest without K8s metadata.
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        del manifest["metadata"]
        res.manifests["some-name"] = manifest
        _, err = gen.appinfo_from_manifests(cfg, {"Deployment": res})
        assert err

        # Must reject corrupt manifest.
        res.manifests["some-name"] = {"not": "a deployment"}
        _, err = gen.appinfo_from_manifests(cfg, {"Deployment": res})
        assert err

    def test_info_from_manifests_invalid_labels(self):
        """Test function must abort if the manifests lack the essential labels.

        The actual check if the labels are relevant happens in `get_metainfo`
        which has its own test suite. As such, we only need to do some basic
        validations that the output of that function is correctly used.

        """
        name, ns, env = "demo", "default", "stg"

        # Must accept minimal specimen.
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
        )
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        _, err = gen.appinfo_from_manifests(cfg, convert_manifest(manifest))
        assert not err

        # Must reject manifest without labels.
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        del manifest["metadata"]["labels"]
        _, err = gen.appinfo_from_manifests(cfg, convert_manifest(manifest))
        assert err

        # Must reject manifest with missing `env` label.
        manifest = gen.deployment_manifest(cfg, app_info, False, base=None)
        del manifest["metadata"]["labels"][cfg.env_label]
        _, err = gen.appinfo_from_manifests(cfg, convert_manifest(manifest))
        assert err

    def test_generate_deployment_new(self):
        # Input.
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=gen.DeploymentInfo(
                    isFlux=False,
                    useResources=True,
                    resources=gen.K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=81)),
                    useLivenessProbe=True,
                    useReadinessProbe=True,
                    envVars=[
                        K8sEnvVar(name="key", value="value"),
                        K8sEnvVar(
                            name="fieldref",
                            valueFrom={
                                "fieldRef": {"apiVersion": "v1", "fieldPath": "blah"}
                            },
                        ),
                    ],
                    image="image:tag",
                    name="container-name",
                )
            ),
        )

        # Generate a brand new deployment manifest.
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert obj["apiVersion"] == "apps/v1"
        assert obj["kind"] == "Deployment"
        assert obj["metadata"]["name"] == name
        assert obj["metadata"]["namespace"] == ns

        expected_labels = gen.resource_labels(cfg, app_info.metadata, False)
        assert obj["metadata"]["labels"] == expected_labels
        assert obj["spec"]["template"]["metadata"]["labels"] == expected_labels

        container = obj["spec"]["template"]["spec"]["containers"][0]
        assert container["readinessProbe"] and container["readinessProbe"]["httpGet"]
        assert container["readinessProbe"]["httpGet"]["path"] == "/ready"
        assert container["readinessProbe"]["httpGet"]["port"] == 80
        assert container["livenessProbe"] and container["livenessProbe"]["httpGet"]
        assert container["livenessProbe"]["httpGet"]["path"] == "/live"
        assert container["livenessProbe"]["httpGet"]["port"] == 81

        assert container["resources"] == {
            "requests": {"cpu": "100m", "memory": "110M"},
            "limits": {"cpu": "200m", "memory": "220M"},
        }
        assert container["env"] == [
            {"name": "key", "value": "value"},
            dict(
                name="fieldref",
                valueFrom={"fieldRef": {"apiVersion": "v1", "fieldPath": "blah"}},
            ),
        ]
        assert container["image"] == "image:tag"
        assert container["name"] == "container-name"

        # Must not specify apiVersion and kind of Pod.
        assert "apiVersion" not in obj["spec"]["template"]
        assert "kind" not in obj["spec"]["template"]

    def test_generate_deployment_new_empty_cpumem(self):
        # Input.
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
        )
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)

        # Resources field must be an empty dict.
        assert obj["spec"]["template"]["spec"]["containers"][0]["resources"] == {}

    def test_generate_deployment_new_disabled_cpumem(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    useResources=False,
                )
            ),
        )

        # Must not generate any resources because `useResources` was disabled.
        app_info.primary.deployment.useResources = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert obj["spec"]["template"]["spec"]["containers"][0]["resources"] == {}

        # This time, must generate the resources because `useResources` was enabled.
        app_info.primary.deployment.useResources = True
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert obj["spec"]["template"]["spec"]["containers"][0]["resources"] == {
            "limits": {"cpu": "200m", "memory": "220M"},
            "requests": {"cpu": "100m", "memory": "110M"},
        }

    def test_generate_deployment_update_existing_disabled_cpumem(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                )
            ),
        )

        # Must not generate any resources because `useResources` was disabled.
        app_info.primary.deployment.useResources = True
        existing = gen.deployment_manifest(cfg, app_info, canary=False, base=None)

        app_info.primary.deployment.useResources = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=existing)

        # This time, must generate the resources because `useResources` was enabled.
        assert obj["spec"]["template"]["spec"]["containers"][0]["resources"] == {}

    def test_generate_deployment_new_disabled_liveness(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                )
            ),
        )

        # Must not generate the liveness probe because `useLivenessProbe` was disabled.
        app_info.primary.deployment.useLivenessProbe = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert "livenessProbe" not in obj["spec"]["template"]["spec"]["containers"][0]

        # Must now generate the liveness probe because `useLivenessProbe` was enabled.
        app_info.primary.deployment.useLivenessProbe = True
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert obj["spec"]["template"]["spec"]["containers"][0]["livenessProbe"] == {
            "httpGet": {"path": "/live", "port": 80}
        }

    def test_generate_deployment_update_existing_disabled_liveness(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                )
            ),
        )

        # Must not generate the liveness probe because `useLivenessProbe` was disabled.
        app_info.primary.deployment.useLivenessProbe = True
        existing = gen.deployment_manifest(cfg, app_info, canary=False, base=None)

        # Must now generate the liveness probe because `useLivenessProbe` was enabled.
        app_info.primary.deployment.useLivenessProbe = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=existing)
        assert "livenessProbe" not in obj["spec"]["template"]["spec"]["containers"][0]

    def test_generate_deployment_new_disabled_readiness(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/live", port=80)
                    ),
                )
            ),
        )

        # Must not generate the readiness probe because `useReadinessProbe` was disabled.
        app_info.primary.deployment.useReadinessProbe = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert "readinessProbe" not in obj["spec"]["template"]["spec"]["containers"][0]

        # Must now generate the readiness probe because `useReadinessProbe` was enabled.
        app_info.primary.deployment.useReadinessProbe = True
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=None)
        assert obj["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] == {
            "httpGet": {"path": "/live", "port": 80}
        }

    def test_generate_deployment_update_existing_disabled_readiness(self):
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                )
            ),
        )

        # Must not generate the readiness probe because `useReadinessProbe` was disabled.
        app_info.primary.deployment.useReadinessProbe = True
        existing = gen.deployment_manifest(cfg, app_info, canary=False, base=None)

        # Must now generate the readiness probe because `useReadinessProbe` was enabled.
        app_info.primary.deployment.useReadinessProbe = False
        obj = gen.deployment_manifest(cfg, app_info, canary=False, base=existing)
        assert "readinessProbe" not in obj["spec"]["template"]["spec"]["containers"][0]

    @pytest.mark.parametrize("has_canary", [False, True])
    def test_generate_service_manifests_new(self, has_canary: bool):
        # Input.
        db = Database()
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(name="main", image="image:primary"),
                useService=False,
                service=AppService(port=80, targetPort=8080),
            ),
        )

        if has_canary:
            app_info.hasCanary = True
            app_info.canary = AppCanary(
                deployment=DeploymentInfo(name="main", image="image:canary"),
                useService=False,
                service=AppService(port=90, targetPort=9090),
            )

        # Must not produce any Service manifests because app has no service.
        manifests = gen.service_manifests(cfg, db, app_info)
        assert len(manifests) == 0

        # Must produce one Service manifest for Primary and Canary.
        app_info.primary.useService = True
        app_info.canary.useService = True
        manifests = gen.service_manifests(cfg, db, app_info)
        assert len(manifests) == 2 if has_canary else 1

        # Must be valid DFH manifest.
        res_name = gen.watch_key(app_info.metadata, False)
        assert is_dfh_manifest(cfg, manifests[res_name])

        primary_svc = K8sService.model_validate(manifests[res_name])
        assert primary_svc.metadata.name == name
        assert primary_svc.metadata.namespace == ns
        assert len(primary_svc.spec.ports) == 1
        assert primary_svc.spec.ports[0].model_dump() == {
            "appProtocol": "http",
            "name": "http2",
            "port": 80,
            "protocol": "TCP",
            "targetPort": 8080,
        }
        assert primary_svc.spec.selector == {"app": name}

        if has_canary:
            canary_name = name + "-canary"
            res_name = gen.watch_key(app_info.metadata, True)
            canary_svc = K8sService.model_validate(manifests[res_name])

            # Must have same namespace and labels.
            assert canary_svc.metadata.namespace == primary_svc.metadata.namespace
            assert canary_svc.metadata.labels == gen.resource_labels(
                cfg, app_info.metadata, True
            )

            # Must have a dedicated name ending in `-canary` and also target
            # dedicated deployment.
            assert canary_svc.metadata.name == canary_name
            assert canary_svc.spec.selector == {"app": canary_name}

            assert canary_svc.spec.ports[0].model_dump() == {
                "appProtocol": "http",
                "name": "http2",
                "port": 90,
                "protocol": "TCP",
                "targetPort": 9090,
            }

    def test_generate_service_manifests_update(self):
        # Input.
        db = Database()
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(name="main", image="image:primary"),
                useService=True,
                service=AppService(port=80, targetPort=8080),
            ),
            canary=AppCanary(
                deployment=DeploymentInfo(name="main", image="image:canary"),
                useService=True,
                service=AppService(port=90, targetPort=9090),
            ),
            hasCanary=True,
        )

        # Produce Service manifests.
        manifests = gen.service_manifests(cfg, db, app_info)
        assert len(manifests) == 2

        # Add artificial labels to the manifests.
        res_name_primary = gen.watch_key(app_info.metadata, False)
        res_name_canary = gen.watch_key(app_info.metadata, True)
        for res_name in (res_name_primary, res_name_canary):
            manifests[res_name]["metadata"]["labels"]["new"] = "label"
            manifests[res_name]["metadata"]["annotations"]["new"] = "annotation"

        # Insert the modified manifests into the database.
        db.apps[name] = {env: DatabaseAppEntry(appInfo=app_info)}
        svc_db = db.apps[name][env].resources["Service"]
        svc_db.manifests[res_name_primary] = manifests[res_name_primary]
        svc_db.manifests[res_name_canary] = manifests[res_name_canary]

        # Produce the manifests again and verify that the labels have survived.
        manifests = gen.service_manifests(cfg, db, app_info)
        assert len(manifests) == 2
        for res_name in (res_name_primary, res_name_canary):
            assert manifests[res_name]["metadata"]["labels"]["new"] == "label"
            assert manifests[res_name]["metadata"]["annotations"]["new"] == "annotation"

    def test_generate_istio_manifests(self):
        # Input.
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                useService=True,
                service=AppService(),
            ),
            canary=AppCanary(
                useService=True,
                service=AppService(),
                trafficPercent=12,
            ),
            hasCanary=True,
        )
        meta = app_info.metadata

        # Generate brand new application manifests since our database is still
        # empty. Must also not have touched the database.
        vs, dr, err = gen.istio_manifests(cfg, app_info)
        assert not err

        # Must have produced one `VirtualService` and one `DestinationRule` manifest.
        assert vs["kind"] == "VirtualService"
        assert dr["kind"] == "DestinationRule"
        assert vs["apiVersion"] == dr["apiVersion"] == "networking.istio.io/v1beta1"

        assert vs["metadata"]["name"] == meta.name
        assert dr["metadata"]["name"] == meta.name
        assert vs["metadata"]["namespace"] == meta.namespace
        assert dr["metadata"]["namespace"] == meta.namespace

        assert vs["metadata"]["labels"] == gen.resource_labels(cfg, meta, False)
        assert dr["metadata"]["labels"] == gen.resource_labels(cfg, meta, False)

        assert vs["spec"]["hosts"] == [name]
        assert len(vs["spec"]["http"]) == 1
        assert len(vs["spec"]["http"][0]["route"]) == 2
        assert vs["spec"]["http"][0]["route"][0] == {
            "destination": dict(host=name, subset="primary"),
            "weight": 88,
        }
        assert vs["spec"]["http"][0]["route"][1] == {
            "destination": dict(host=name, subset="canary"),
            "weight": 12,
        }

        assert dr["spec"]["host"] == name
        assert len(dr["spec"]["subsets"]) == 2
        assert dr["spec"]["subsets"][0]["name"] == "primary"
        assert dr["spec"]["subsets"][0]["labels"] == {"deployment-type": "primary"}
        assert dr["spec"]["subsets"][1]["name"] == "canary"
        assert dr["spec"]["subsets"][1]["labels"] == {"deployment-type": "canary"}

    def test_generate_istio_manifests_invalid(self):
        # Input.
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                useService=True,
                service=AppService(),
            ),
            canary=AppCanary(
                useService=True,
                service=AppService(),
                trafficPercent=12,
            ),
            hasCanary=True,
        )

        # Must pass for valid percentages in range [0, 100].
        for per in (0, 50, 100):
            app_info.canary.trafficPercent = per
            _, _, err = gen.istio_manifests(cfg, app_info)
            assert not err

        # Must fail for invalid traffic percentages.
        for per in (-1, 101):
            app_info.canary.trafficPercent = per
            _, _, err = gen.istio_manifests(cfg, app_info)
            assert err

        # Must fail if the app has no canaries.
        app_info.hasCanary = False
        app_info.canary.trafficPercent = 50
        _, _, err = gen.istio_manifests(cfg, app_info)
        assert err

    def test_manifests_from_appinfo_primary_only(self):
        # Input.
        ns, name, env = "default", "fooapp", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    isFlux=False,
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    useResources=True,
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                    useLivenessProbe=True,
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                    useReadinessProbe=True,
                    envVars=[K8sEnvVar(name="key", value="value")],
                ),
                useService=True,
                service=AppService(port=100, targetPort=200),
            ),
        )

        # Generate brand new application manifests since our database is still
        # empty. Must also not have touched the database.
        db = Database()
        obj, err = gen.manifests_from_appinfo(cfg, app_info, db)
        assert not err
        assert db == Database()

        # Must have produced one Deployment and one Service manifest.
        res_name = gen.watch_key(app_info.metadata, False)
        assert set(obj.resources["Deployment"].manifests.keys()) == {res_name}
        assert set(obj.resources["Service"].manifests.keys()) == {res_name}

    def test_manifests_from_appinfo_primary_and_canary(self):
        # Input.
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    isFlux=False,
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    useResources=True,
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                    useLivenessProbe=True,
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                    useReadinessProbe=True,
                    envVars=[K8sEnvVar(name="key", value="value")],
                )
            ),
            canary=AppCanary(
                deployment=DeploymentInfo(
                    isFlux=False,
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    useResources=True,
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=90)),
                    useLivenessProbe=True,
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=90)
                    ),
                    useReadinessProbe=True,
                    envVars=[K8sEnvVar(name="key", value="value")],
                )
            ),
            hasCanary=True,
        )

        # Generate brand new application manifests since our database is still
        # empty. Must also not have touched the database.
        db = Database()
        obj, err = gen.manifests_from_appinfo(cfg, app_info, db)
        assert not err
        assert db == Database()

        # Must have produced two deployment manifest.
        deployments = obj.resources["Deployment"].manifests
        primary = gen.watch_key(app_info.metadata, False)
        canary = gen.watch_key(app_info.metadata, True)
        assert set(deployments.keys()) == {primary, canary}

        assert deployments[primary]["metadata"]["name"] == name
        assert deployments[canary]["metadata"]["name"] == f"{name}-canary"

        assert deployments[primary]["metadata"]["labels"] == gen.resource_labels(
            cfg, app_info.metadata, False
        )
        assert deployments[canary]["metadata"]["labels"] == gen.resource_labels(
            cfg, app_info.metadata, True
        )

        assert (
            deployments[primary]["spec"]["template"]["spec"]["containers"][0][
                "livenessProbe"
            ]["httpGet"]["port"]
            == 80
        )
        assert (
            deployments[canary]["spec"]["template"]["spec"]["containers"][0][
                "livenessProbe"
            ]["httpGet"]["port"]
            == 90
        )

    def test_manifests_from_appinfo_istio_resources(self):
        # Input.
        name, ns, env = "demo", "default", "stg"
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(useService=True),
            canary=AppCanary(useService=True),
            hasCanary=True,
        )

        # Generate brand new Istio manifests.
        obj, err = gen.manifests_from_appinfo(cfg, app_info, Database())
        assert not err

        # Must have produced one `VirtualService` and one `DestinationRule` manifest.
        assert len(obj.resources["VirtualService"].manifests) == 1
        assert len(obj.resources["DestinationRule"].manifests) == 1

        # Must abort for invalid traffic percentages.
        app_info.canary.trafficPercent = 200
        obj, err = gen.manifests_from_appinfo(cfg, app_info, Database())
        assert err

    @pytest.mark.parametrize("has_canary", [False, True])
    @pytest.mark.parametrize("use_service", [False, True])
    @pytest.mark.parametrize("has_virtsvc", [False, True])
    def test_app_info_to_manifests_and_back(
        self, has_virtsvc: bool, use_service: bool, has_canary: bool
    ):
        """Ensure that we can reverse engineer `AppInfo` from the generated manifests.

        This is DFH is crucial for importing applications albeit superfluous for DFH itself.

        """
        db = Database()
        name, ns, env = "demo", "default", "stg"

        # Base application with just a primary deployment.
        app_src = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/foo", port=100),
                        initialDelaySeconds=1,
                        periodSeconds=2,
                    ),
                    useReadinessProbe=True,
                    name="main",
                    image="image:primary",
                ),
            ),
        )

        # Optional: add Canary deployment.
        if has_canary:
            app_src.hasCanary = True
            app_src.canary = AppCanary(
                deployment=DeploymentInfo(
                    livenessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/foo", port=200),
                        initialDelaySeconds=2,
                        periodSeconds=4,
                    ),
                    useLivenessProbe=True,
                    name="main",
                    image="image:canary",
                ),
                trafficPercent=20,
            )

        # Optional: add a K8s service.
        if use_service:
            app_src.primary.useService = True
            app_src.primary.service = AppService(port=80, targetPort=8080)
            if has_canary:
                app_src.canary.useService = True
                app_src.canary.service = AppService(port=90, targetPort=9090)

        # Generate the manifests. This must succeed.
        manifests, err = gen.manifests_from_appinfo(cfg, app_src, db)
        assert not err

        if has_canary and not has_virtsvc:
            manifests.resources["VirtualService"].manifests.clear()
            app_src.canary.trafficPercent = 0

        # Reconstruct `AppInfo` from the just generated manifest. This must succeed.
        app_dst, err = gen.appinfo_from_manifests(cfg, manifests.resources)
        assert not err

        # Compare JSON models (easier to read when test fails.)
        assert app_src.model_dump_json(indent=4) == app_dst.model_dump_json(indent=4)

        # Compare the full Pydantic models.
        assert app_src == app_dst

    def test_square_config(self):
        srv_cfg, err = dfh.api.compile_server_config()
        assert not err
        srv_cfg.kubeconfig = Path("/foo/bar.yaml")
        srv_cfg.kubecontext = "blah"

        sq_cfg = gen.square_config(srv_cfg, "myapp", "myns", "stg")
        assert sq_cfg.selectors.namespaces == ["myns"]
        assert sq_cfg.selectors.labels == ["app.kubernetes.io/name=myapp", "env=stg"]
        assert sq_cfg.selectors.kinds == {"Deployment", "Service"}
        assert sq_cfg.kubeconfig == Path("/foo/bar.yaml")
        assert sq_cfg.kubecontext == "blah"


class TestGenerateIntegration:
    async def test_compile_plan(self):
        # Input.
        name, ns, env = "fooapp", "default", "stg"

        cfg = get_server_config()
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
            primary=AppPrimary(
                deployment=DeploymentInfo(
                    isFlux=False,
                    resources=K8sRequestLimit(
                        requests=K8sResourceCpuMem(cpu="100m", memory="110M"),
                        limits=K8sResourceCpuMem(cpu="200m", memory="220M"),
                    ),
                    useResources=True,
                    livenessProbe=K8sProbe(httpGet=K8sProbeHttp(path="/live", port=80)),
                    readinessProbe=K8sProbe(
                        httpGet=K8sProbeHttp(path="/ready", port=80)
                    ),
                    envVars=[K8sEnvVar(name="key", value="value")],
                )
            ),
        )

        # Must create one Deployment because the DB is empty.
        sq_plan, err = await gen.compile_plan(cfg, app_info, Database())
        assert not err
        assert len(sq_plan.create) == 1
        assert len(sq_plan.patch) == len(sq_plan.delete) == 0

        fe_plan = gen.compile_frontend_plan(sq_plan)
        assert len(fe_plan.create) == 1
        assert len(fe_plan.patch) == len(fe_plan.delete) == 0

        # Insert an app into our DB.
        db = Database()
        manifests, err = gen.manifests_from_appinfo(cfg, app_info, db)
        assert not err

        db.apps = {name: {env: DatabaseAppEntry(appInfo=app_info)}}
        db_man = db.apps[name][env].resources["Deployment"].manifests
        for manifest in manifests.resources["Deployment"].manifests.values():
            db_man[gen.watch_key(app_info.metadata, False)] = manifest

        # Must not create anything if the new app is identical to the old one.
        sq_plan, err = await gen.compile_plan(cfg, app_info, db)
        assert not err
        assert len(sq_plan.patch) == len(sq_plan.create) == len(sq_plan.delete) == 0

        fe_plan = gen.compile_frontend_plan(sq_plan)
        assert len(fe_plan.create) == 0
        assert len(fe_plan.patch) == len(fe_plan.delete) == 0

        # Must patch the deployment if the new app config differs from the existing one.
        app_info.primary.deployment.resources.limits.memory = "5000"
        sq_plan, err = await gen.compile_plan(cfg, app_info, db)
        assert not err
        assert len(sq_plan.patch) == 1
        assert len(sq_plan.create) == len(sq_plan.delete) == 0

        fe_plan = gen.compile_frontend_plan(sq_plan)
        assert len(fe_plan.patch) == 1
        assert len(fe_plan.create) == len(fe_plan.delete) == 0

    async def test_compile_plan_skip_pods(self):
        """Plan must never include pods."""
        # Input.
        name, ns, env = "demo", "default", "stg"

        cfg = get_server_config()
        app_info = AppInfo(
            metadata=AppMetadata(name=name, env=env, namespace=ns),
        )

        # Manually add a Pod to or app.
        db = Database()
        db.apps = {name: {env: DatabaseAppEntry(appInfo=app_info)}}
        db_res = db.apps[name][env].resources["Pod"].manifests
        db_res[gen.watch_key(app_info.metadata, False)] = {"kind": "Pod"}

        # The plan must not include the pod even though it exists in the app's resources.
        sq_plan, err = await gen.compile_plan(cfg, app_info, db)
        assert not err
        assert len(sq_plan.create) == 1
        assert len(sq_plan.patch) == len(sq_plan.delete) == 0
