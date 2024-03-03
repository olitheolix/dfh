from typing import List, Tuple

from dfh.models import K8sEnvVar

# Convenience: these are the automatically injected environment variables based
# on Pod labels.
RESERVED_FIELDREF_ENVS = (
    "POD_ID",
    "POD_NAME",
    "POD_NAMESPACE",
    "POD_VERSION",
    "POD_IP",
)


def pod_fieldref_envs() -> List[K8sEnvVar]:
    """Return default env vars that are sourced from Pod labels."""
    kv: List[Tuple[str, str]] = [
        ("POD_ID", "metadata.uid"),
        ("POD_NAME", "metadata.name"),
        ("POD_NAMESPACE", "metadata.namespace"),
        ("POD_VERSION", "metadata.labels['version']"),
        ("POD_IP", "status.podIP"),
    ]

    env_vars = []
    for name, value in kv:
        env_vars.append(
            K8sEnvVar(
                name=name,
                valueFrom=dict(fieldRef=dict(apiVersion="v1", fieldPath=value)),
            )
        )
    return env_vars


def pod_security_context() -> dict:
    ctx = dict(
        allowPrivilegeEscalation=False,
        capabilities=dict(drop=["ALL"]),
        privileged=False,
        readOnlyRootFilesystem=True,
        runAsGroup=3000,
        runAsNonRoot=True,
        runAsUser=1000,
    )

    return ctx
