from typing import Dict, Tuple

from dfh.models import AppMetadata, ServerConfig


def is_dfh_manifest(cfg: ServerConfig, manifest: dict) -> bool:
    """Return `True` if the `manifest` is managed by DFH."""
    # Get the labels.
    try:
        labels: Dict[str, str] = manifest["metadata"]["labels"]
    except KeyError:
        return False

    # These labels defined whether or not DFH owns this manifest.
    expected_labels = (
        cfg.env_label,
        "app.kubernetes.io/name",
        "app.kubernetes.io/managed-by",
    )

    # All expected labels must exist and be non-empty.
    for name in expected_labels:
        if labels.get(name, "") == "":
            return False

    # Manifest must be managed by DFH.
    if labels["app.kubernetes.io/managed-by"] != cfg.managed_by:
        return False
    return True


def get_metainfo(cfg, manifest: dict) -> Tuple[AppMetadata, bool]:
    if not is_dfh_manifest(cfg, manifest):
        return AppMetadata(), True

    namespace = manifest["metadata"].get("namespace", "")
    env = manifest["metadata"]["labels"][cfg.env_label]
    app_name = manifest["metadata"]["labels"]["app.kubernetes.io/name"]

    # Compile MetaInfo for this manifest. This is similar but not identical to
    # the Metadata of each manifest.
    return AppMetadata(name=app_name, env=env, namespace=namespace), False
