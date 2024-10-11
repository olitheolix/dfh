from typing import Dict, List, Tuple

from square.dtypes import FiltersKind

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
    """Return a generic pod security context."""
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


def topology_spread(label_selectors: Dict[str, str]) -> List[dict]:
    """Return a generic topology spread."""
    out = []
    topology_keys = ("topology.kubernetes.io/zone", "kubernetes.io/hostname")
    for key in topology_keys:
        constraint = dict(
            labelSelector=dict(matchLabels=label_selectors.copy()),
            maxSkew=1,
            topologyKey=key,
            whenUnsatisfiable="ScheduleAnyway",
        )
        out.append(constraint)
    return out


def square_filters() -> Dict[str, FiltersKind]:
    filters = {
        "Deployment": [
            {
                "metadata": [
                    {
                        "annotations": [
                            "autoscaling.alpha.kubernetes.io/conditions",
                            "deployment.kubernetes.io/revision",
                            "kubectl.kubernetes.io/last-applied-configuration",
                            "kubernetes.io/change-cause",
                        ]
                    },
                    "creationTimestamp",
                    "generation",
                    "managedFields",
                    "resourceVersion",
                    "selfLink",
                    "uid",
                ]
            },
            {"spec": [{"template": [{"metadata": ["creationTimestamp"]}]}]},
            "status",
        ],
        "Service": [
            {
                "metadata": [
                    {
                        "annotations": [
                            "kubectl.kubernetes.io/last-applied-configuration",
                            "kubernetes.io/change-cause",
                        ]
                    },
                    "creationTimestamp",
                    "generation",
                    "managedFields",
                    "resourceVersion",
                    "selfLink",
                    "uid",
                ]
            },
            {
                "spec": [
                    "clusterIP",
                    "clusterIPs",
                    "internalTrafficPolicy",
                    "ipFamilies",
                    "ipFamilyPolicy",
                    "sessionAffinity",
                    "type",
                ]
            },
            "status",
        ],
    }
    return filters
