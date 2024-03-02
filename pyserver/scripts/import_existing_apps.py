"""Try to import already existing apps from the dfh.

Usage:
   - Adjust the settings in `get_server_confg`.
   - Must be called from parent folder like so:
      $ PYTHONPATH=`pwd` pipenv run python scripts/import_existing_apps.py

"""

import asyncio
from pathlib import Path
from typing import Dict

import httpx

import dfh.generate
import dfh.k8s
import dfh.watch
from dfh.generate import watch_key
from dfh.models import (
    AppMetadata,
    GeneratedManifests,
    ServerConfig,
    WatchedResource,
)


def get_server_config():
    return ServerConfig(
        kubeconfig=Path("/tmp/kind-kubeconf.yaml"),
        kubecontext="kind-kind",
        managed_by="dfh",
        env_label="env",
    )


async def main():
    # Create K8s client.
    cfg = get_server_config()
    k8scfg, err = dfh.watch.create_cluster_config(cfg.kubeconfig, cfg.kubecontext)
    assert not err

    apps: Dict[tuple, Dict[str, WatchedResource]] = {}

    # Iterate over all manifests and group them by DFH metadata. Drop all
    # manifests that do not appear to be managed by DFH.
    for kind, res in GeneratedManifests().resources.items():
        # Fetch all resources of the current `kind`.
        resp, err = await dfh.k8s.get(k8scfg, res.path)
        assert not err

        # Discard all manifest that do not belong to DFH and group the rest by
        # their `AppMetadata`.
        for manifest in resp["items"]:
            manifest["kind"] = kind
            manifest["apiVersion"] = res.apiVersion

            # Extract meta information, eg name, env and namespace. This will fail
            # if the manifest is not managed by DFH.
            meta, err = dfh.watch.get_metainfo(cfg, manifest)
            if err:
                continue

            # Hashable grouping key.
            key = (meta.name, meta.env, meta.namespace)

            # Ensure groups[key][kind] exists.
            if key not in apps:
                apps[key] = {kind: WatchedResource.model_validate(res.model_dump())}

            if kind not in apps[key]:
                apps[key][kind] = WatchedResource.model_validate(res.model_dump())

            # Add the manifest to the current app group.
            apps[key][kind].manifests[watch_key(meta, False)] = manifest

    # Try to reconstruct the `AppInfo` from the manifests we have gathered and
    # insert it into DFH.
    for key, app in apps.items():
        # Reverse engineer an `DeploymentInfo` from the manifest.
        app_info, err = dfh.generate.appinfo_from_manifests(cfg, app)
        assert not err

        # Reconstruct the AppMetadata for the app.
        meta = AppMetadata(name=key[0], env=key[1], namespace=key[2])

        # Compile a full `AppInfo` model and ask DFH to add it to its database.
        url = f"http://localhost:5001/api/crt/v1/apps/{meta.name}/{meta.env}"
        resp = await httpx.AsyncClient().post(url, json=app_info.model_dump())
        if resp.status_code == 409:
            print(f"Skipped: {meta.name}/{meta.env}")
            continue
        assert resp.status_code == 200, resp.status_code

        print(f"Added  : {meta}")


if __name__ == "__main__":
    asyncio.run(main())
