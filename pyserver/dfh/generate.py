import copy
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import pydantic
import square
import square.dtypes
import square.k8s
import square.manio
import yaml

import dfh.defaults
import dfh.models
import dfh.square_types
from dfh.manifest_utilities import get_metainfo
from dfh.models import (
    AppCanary,
    AppInfo,
    AppMetadata,
    AppPrimary,
    AppService,
    Database,
    DeploymentInfo,
    GeneratedManifests,
    K8sDeployment,
    K8sDestinationRule,
    K8sEnvVar,
    K8sMetadata,
    K8sProbe,
    K8sRequestLimit,
    K8sService,
    K8sServicePort,
    K8sVirtualService,
    ServerConfig,
    WatchedResource,
)

logit = logging.getLogger("app")


def k8s_resource_name(meta: AppMetadata, canary: bool):
    """Return K8s resource name.

    The assumption is that the K8s resource names are agnostic to the resource
    kind, ie Deployment, Services, HPAs etc all use the same name for the same app.

    """
    return f"{meta.name}-canary" if canary else meta.name


def watch_key(meta: AppMetadata, canary: bool):
    """Return the key we use to index K8s resources for individual apps.

    The assumption is that the K8s resource names are agnostic to the resource
    kind, ie Deployment, Services, HPAs etc all use the same name for the same app.

    """
    k8s_name = k8s_resource_name(meta, canary)
    return f"{meta.namespace}/{k8s_name}"


def resource_labels(
    cfg: ServerConfig, meta: AppMetadata, is_canary: bool
) -> Dict[str, str]:
    labels = {
        "app": meta.name,
        cfg.env_label: meta.env,
        "app.kubernetes.io/name": meta.name,
        "app.kubernetes.io/managed-by": cfg.managed_by,
        "deployment-type": "canary" if is_canary else "primary",
    }
    return labels


def deployment_manifest(
    cfg: ServerConfig, app: AppInfo, canary: bool, base: dict | None
) -> dict:
    """Produce K8s deployment manifests for `app`.

    Set `base=None` to create a new deployment from scratch, or provide an
    existing one to upsert the changes into it.

    """
    # Load a template if the user did not provide a base manifest to upsert into.
    if base:
        rawmanifest = copy.deepcopy(base)
    else:
        rawmanifest = yaml.safe_load(
            Path("support/deployment_template.yaml").read_text()
        )

    labels = resource_labels(cfg, app.metadata, canary)

    # Parse the base manifest and fill out the Deployment info.
    manifest = K8sDeployment.model_validate(rawmanifest)
    manifest.apiVersion = "apps/v1"
    manifest.kind = "Deployment"
    manifest.metadata = K8sMetadata(
        name=k8s_resource_name(app.metadata, canary),
        namespace=app.metadata.namespace,
        labels=labels,
    )

    if not manifest.spec.selector:
        manifest.spec.selector = {"matchLabels": labels}
    manifest.spec.template.metadata = K8sMetadata(labels=labels)

    # Spec the application container of the Pod.
    dply = app.canary.deployment if canary else app.primary.deployment
    container = manifest.spec.template.spec.containers[0]
    container.name = dply.name
    container.image = dply.image
    container.command = dply.command.split()
    container.args = dply.args.split()
    container.resources = dply.resources if dply.useResources else K8sRequestLimit()
    container.readinessProbe = (
        dply.readinessProbe if dply.useReadinessProbe else K8sProbe()
    )
    container.livenessProbe = (
        dply.livenessProbe if dply.useLivenessProbe else K8sProbe()
    )
    container.env = dply.envVars + dfh.defaults.pod_fieldref_envs()
    container.securityContext = dfh.defaults.pod_security_context()

    # Dump the model.
    out = manifest.model_dump(exclude_defaults=True)

    # --- Post Processing ---
    # Replace missing `spec.template.containers[].resources` with an empty dict
    # to avoid a pointless diffs. K8s always reports an empty map if no
    # resources were specified.
    for container in out["spec"]["template"]["spec"]["containers"]:
        if dply.useResources:
            container["resources"] = container.get("resources", {})
        else:
            container["resources"] = {}

    out["spec"]["template"]["spec"]["topologySpreadConstraints"] = (
        dfh.defaults.topology_spread({"app": app.metadata.name})
    )

    return out


def service_manifests(
    cfg: ServerConfig, db: Database, app_info: AppInfo
) -> Dict[str, dict]:
    svc_info = app_info.primary

    out: Dict[str, dict] = {}
    meta = app_info.metadata

    prim_canary: List[Tuple[AppPrimary | AppCanary, bool]] = [
        (app_info.primary, False),
        (app_info.canary, True),
    ]

    for svc_info, is_canary in prim_canary:  # type: ignore
        if not svc_info.useService:
            continue

        labels = resource_labels(cfg, app_info.metadata, is_canary)

        k8s_name = k8s_resource_name(meta, is_canary)
        svc = K8sService(apiVersion="v1", kind="Service")
        svc.metadata = K8sMetadata(
            name=k8s_name,
            namespace=meta.namespace,
            labels=labels,
        )

        port = K8sServicePort(
            name="http2",
            appProtocol="http2",
            port=svc_info.service.port,
            targetPort=svc_info.service.targetPort,
            protocol="TCP",
        )
        svc.spec.ports = [port]
        svc.spec.selector = {"app": k8s_name}

        db_key = watch_key(meta, is_canary)
        try:
            old = db.apps[meta.name][meta.env].resources["Service"].manifests[db_key]
            old = old["metadata"]
            svc.metadata.labels = old["labels"] | svc.metadata.labels
            svc.metadata.annotations = old["annotations"] | svc.metadata.annotations
        except KeyError:
            pass

        out[db_key] = svc.model_dump()

    return out


def istio_manifests(cfg: ServerConfig, app_info: AppInfo) -> Tuple[dict, dict, bool]:
    """Produce the VirtualService and Destination to support a Canary deployment."""
    # Convenience.
    meta = app_info.metadata
    name = app_info.metadata.name

    # Sanity checks.
    if not app_info.hasCanary:
        logit.error(f"app {meta} has no canary")
        return {}, {}, True

    if not (0 <= app_info.canary.trafficPercent <= 100):
        logit.error(f"invalid canary percentage {app_info.canary.trafficPercent}")
        return {}, {}, True

    weight_canary = app_info.canary.trafficPercent
    weight_primary = 100 - weight_canary

    # Route entries for VirtualService.spec.http.route
    route_primary = dict(
        destination=dict(host=name, subset="primary"),
        weight=weight_primary,
    )
    route_canary = dict(
        destination=dict(host=name, subset="canary"),
        weight=weight_canary,
    )

    # Construct the VirtualService to split traffic among two hard coded
    # DestinationRule subsets.
    vs_spec = {
        "hosts": [name],
        "http": [{"route": [route_primary, route_canary]}],
    }
    vs = K8sVirtualService(
        apiVersion="networking.istio.io/v1beta1",
        kind="VirtualService",
        metadata=K8sMetadata(
            name=name,
            namespace=meta.namespace,
            labels=resource_labels(cfg, meta, False),
        ),
        spec=K8sVirtualService.Spec.model_validate(vs_spec),
    )

    # Construct the DestinationRule for two hard coded subsets.
    dr_spec = {
        "host": name,
        "subsets": [
            {"name": "primary", "labels": {"deployment-type": "primary"}},
            {"name": "canary", "labels": {"deployment-type": "canary"}},
        ],
    }
    dr = K8sDestinationRule(
        apiVersion="networking.istio.io/v1beta1",
        kind="DestinationRule",
        metadata=K8sMetadata(
            name=name,
            namespace=meta.namespace,
            labels=resource_labels(cfg, meta, False),
        ),
        spec=K8sDestinationRule.Spec.model_validate(dr_spec),
    )

    return (vs.model_dump(), dr.model_dump(), False)


def manifests_from_appinfo(
    cfg: ServerConfig, app_info: AppInfo, db: Database
) -> Tuple[GeneratedManifests, bool]:
    """Produce all app manifests for the `userapp`.

    Merges the `userapp` information into the existing manifests. If there are
    no such manifest it will produce new ones from a template.

    """
    # Convenience.
    meta = app_info.metadata
    name, env = meta.name, meta.env

    # Initialise output. Function will populate it with manifests as it proceeds.
    out = GeneratedManifests()

    # Get the existing deployment manifest for primary and Canary. If they do
    # not exist yet then we set them to `None` and generate new ones from
    # templates later.
    primary = watch_key(meta, False)
    canary = watch_key(meta, True)
    try:
        app_data = db.apps[name][env]
        primary_base = app_data.resources["Deployment"].manifests.get(primary, None)
        canary_base = app_data.resources["Deployment"].manifests.get(canary, None)
    except KeyError:
        primary_base = None
        canary_base = None

    # Add the primary deployment.
    dm = deployment_manifest(cfg, app_info, canary=False, base=primary_base)
    out.resources["Deployment"].manifests[primary] = dm

    # Add the canary deployment if we have one.
    if app_info.hasCanary:
        dm = deployment_manifest(cfg, app_info, canary=True, base=canary_base)
        out.resources["Deployment"].manifests[canary] = dm

        vs, dr, err = istio_manifests(cfg, app_info)
        if err:
            return GeneratedManifests(), True
        out.resources["VirtualService"].manifests[primary] = vs
        out.resources["DestinationRule"].manifests[primary] = dr

    # Add service manifests.
    for name, manifest in service_manifests(cfg, db, app_info).items():
        out.resources["Service"].manifests[name] = manifest

    return out, False


def appinfo_from_manifests(
    cfg: ServerConfig,
    k8s_resources: Dict[str, WatchedResource],
) -> Tuple[AppInfo, bool]:
    """Reverse engineer the `AppInfo` from a group of K8s manifests."""
    out = AppInfo(hasCanary=False)

    # For reference to validate the `apiVersion`.
    factory = dfh.models.factory_WatchedResource()

    # Validate these resource types with their respective Pydantic models.
    kinds = (("Deployment", K8sDeployment), ("Service", K8sService))

    # Validate all manifests.
    all_metadata = []
    for kind, Model in kinds:
        if kind not in k8s_resources:
            k8s_resources[kind] = WatchedResource(apiVersion="", kind=kind, path="")

        for manifest in k8s_resources[kind].manifests.values():
            if manifest.get("kind", "") != kind:
                logit.error(f"Invalid {kind} manifest: .kind")
                return AppInfo(), True

            # Return unless the model compiles.
            try:
                model = Model.model_validate(manifest)  # type: ignore
            except pydantic.ValidationError as err:
                logit.error(f"Invalid {kind} manifest: {err}")
                return AppInfo(), True

            # Return unless this is 1) a valid manifest and 2) tracked by us.
            try:
                assert model.kind == kind
                assert model.apiVersion == factory[kind].apiVersion
                meta, err2 = get_metainfo(cfg, manifest)
                assert not err2
            except AssertionError:
                logit.error(f"Invalid {kind} manifest: cannot extract metadata")
                return AppInfo(), True

            all_metadata.append(meta)
            del manifest
        del kind, Model

    if len(all_metadata) == 0:
        logit.info("Nothing to import")
        return AppInfo(), False

    # Abort unless all manifests produced the same metadata for the app.
    meta = all_metadata[0]
    for _ in all_metadata:
        assert _ == meta
    out.metadata = meta
    del all_metadata

    # Compile the primary/canary deployment info.
    reseved_envs = set(dfh.defaults.RESERVED_FIELDREF_ENVS)
    for manifest in k8s_resources["Deployment"].manifests.values():
        model = K8sDeployment.model_validate(manifest)
        container = model.spec.template.spec.containers[0]
        envVars = [K8sEnvVar(name=el.name, value=el.value) for el in container.env]

        # Remove all the reserved env vars that the user cannot control
        envVars = [_ for _ in envVars if _.name not in reseved_envs]

        deploy_info = DeploymentInfo(
            isFlux=False,
            resources=container.resources,
            useResources=(container.resources != K8sRequestLimit()),
            envVars=envVars,
            readinessProbe=container.readinessProbe,
            livenessProbe=container.livenessProbe,
            useLivenessProbe=(container.livenessProbe != K8sProbe()),
            useReadinessProbe=(container.readinessProbe != K8sProbe()),
            image=container.image,
            name=container.name,
            command=str.join(" ", container.command),
            args=str.join(" ", container.args),
        )

        if model.metadata.labels.get("deployment-type", "") == "canary":
            # Sanity check: there can only be one canary.
            assert out.hasCanary is False

            out.hasCanary = True
            out.canary.deployment = deploy_info

            # Check if we have a VirtualService and if we can extract the
            # traffic percentage from it. Assume the canary has no traffic if
            # that is impossible.
            prim_key = watch_key(meta, False)
            try:
                vs = k8s_resources["VirtualService"].manifests[prim_key]
                primary_weight = vs["spec"]["http"][0]["route"][0]["weight"]
            except (KeyError, IndexError):
                primary_weight = 100

            out.canary.trafficPercent = 100 - primary_weight
        else:
            out.primary.deployment = deploy_info

    # Compile the primary/canary service info.
    for manifest in k8s_resources["Service"].manifests.values():
        model = K8sService.model_validate(manifest)
        svc = AppService(
            port=model.spec.ports[0].port,
            targetPort=model.spec.ports[0].targetPort,
        )
        if model.metadata.labels.get("deployment-type", "") == "canary":
            out.canary.useService = True
            out.canary.service = svc
        else:
            out.primary.useService = True
            out.primary.service = svc

    return out, False


async def compile_plan(
    cfg: ServerConfig, new_app: AppInfo, db: Database, remove: bool = False
) -> Tuple[square.dtypes.DeploymentPlan, bool]:

    # Convenience.
    name, ns, env = (
        new_app.metadata.name,
        new_app.metadata.namespace,
        new_app.metadata.env,
    )

    square_cfg = square_config(cfg, name, ns, env)
    sq_client, err = await square.k8s.cluster_config(
        cfg.kubeconfig,
        cfg.kubecontext,
        conparams=square.dtypes.ConnectionParameters(read=600, write=600, pool=600),
    )
    assert not err

    # Compile the manifests into Square data structures and treat
    # them as the `local` ones.
    local_manifests: square.dtypes.SquareManifests = {}
    if not remove:
        # Generate the deployment manifests (primary and canary).
        new_manifests, err = manifests_from_appinfo(cfg, new_app, db)
        assert not err

        for kind in new_manifests.resources:
            if kind == "Pod":
                continue
            for manifest in new_manifests.resources[kind].manifests.values():
                local_manifests[square.manio.make_meta(manifest)] = manifest

    # Get a handle the app's resources assuming the app exists in DFH.
    server_manifests: square.dtypes.SquareManifests = {}
    try:
        server_res = db.apps[name][env].resources
    except KeyError:
        server_res = {}

    # Compile the latest set of resources from K8s into Square data structures
    # and treat them as the `server` ones.
    for kind in server_res:
        if kind == "Pod":
            continue
        for manifest in server_res[kind].manifests.values():
            server_manifests[square.manio.make_meta(manifest)] = manifest

    # Compute the plan and return it.
    return await square.square.compile_plan(
        square_cfg, sq_client, local_manifests, server_manifests
    )


def compile_frontend_plan(
    sq_plan: square.dtypes.DeploymentPlan,
) -> dfh.square_types.FrontendDeploymentPlan:
    dc = []
    for delta in sq_plan.create:
        meta = dfh.square_types.MetaManifest.model_validate(delta.meta._asdict())
        dc.append(
            dfh.square_types.DeltaCreate(
                url=delta.url, meta=meta, manifest=delta.manifest
            )
        )

    dp = []
    for delta in sq_plan.patch:
        meta = dfh.square_types.MetaManifest.model_validate(delta.meta._asdict())
        dp.append(dfh.square_types.DeltaPatch(meta=meta, diff=delta.diff))

    dd = []
    for delta in sq_plan.delete:
        meta = dfh.square_types.MetaManifest.model_validate(delta.meta._asdict())
        dd.append(
            dfh.square_types.DeltaDelete(
                url=delta.url, meta=meta, manifest=delta.manifest
            )
        )

    plan = dfh.square_types.FrontendDeploymentPlan(
        jobId=str(uuid.uuid4()), create=dc, patch=dp, delete=dd
    )
    return plan


def square_config(
    cfg: ServerConfig, name: str, namespace: str, env: str
) -> square.dtypes.Config:
    sq_cfg = square.dtypes.Config(
        kubeconfig=cfg.kubeconfig,
        kubecontext=cfg.kubecontext,
        folder=Path("/tmp/foo"),
        groupby=square.dtypes.GroupBy(label="app", order=["ns", "label", "kind"]),
        selectors=square.dtypes.Selectors(
            kinds={"Deployment", "Service"},
            labels=[f"app.kubernetes.io/name={name}", f"{cfg.env_label}={env}"],
            namespaces=[namespace],
        ),
        filters=dfh.defaults.square_filters(),
    )
    return sq_cfg
