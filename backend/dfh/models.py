from pathlib import Path
from typing import Any, Dict, List

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ----------------------------------------------------------------------
# Generic Models
# ----------------------------------------------------------------------


class KeyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class NameValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------
class UserToken(BaseModel):
    email: str
    token: str = ""


class UserMe(BaseModel):
    email: str


# ----------------------------------------------------------------------
# Kubernetes
# ----------------------------------------------------------------------


class K8sMetadata(BaseModel):
    name: str = ""
    namespace: str = ""
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    creationTimestamp: Any = None


class K8sServicePort(BaseModel):
    name: str = ""
    port: int = 0
    appProtocol: str = ""
    protocol: str = ""
    targetPort: int = 0


class K8sServiceSpec(BaseModel):
    ports: List[K8sServicePort] = []
    selector: Dict[str, str] = {}


class K8sService(BaseModel):
    apiVersion: str = ""
    kind: str = ""
    metadata: K8sMetadata = K8sMetadata()
    spec: K8sServiceSpec = K8sServiceSpec()


class K8sVirtualService(BaseModel):
    class Spec(BaseModel):
        class Route(BaseModel):
            class Destination(BaseModel):
                class Subset(BaseModel):
                    host: str = ""
                    subset: str = ""

                destination: Subset = Subset()
                weight: int

            route: List[Destination] = []

        hosts: List[str] = []
        http: List[Route] = []

    apiVersion: str = ""
    kind: str = ""
    metadata: K8sMetadata = K8sMetadata()
    spec: Spec = Spec()


class K8sDestinationRule(BaseModel):
    class Spec(BaseModel):
        class Subset(BaseModel):
            name: str = ""
            labels: Dict[str, str] = {}

        host: str = ""
        subsets: List[Subset] = []

    apiVersion: str = ""
    kind: str = ""
    metadata: K8sMetadata = K8sMetadata()
    spec: Spec = Spec()


# Define the Pydantic models
class K8sProbeHttp(BaseModel):
    path: str = ""
    port: int = 0


class K8sProbe(BaseModel):
    httpGet: K8sProbeHttp = K8sProbeHttp()
    initialDelaySeconds: int = -1
    periodSeconds: int = -1
    timeoutSeconds: int = -1
    successThreshold: int = -1
    failureThreshold: int = -1


class K8sResourceCpuMem(BaseModel):
    cpu: str = ""
    memory: str = ""


class K8sRequestLimit(BaseModel):
    requests: K8sResourceCpuMem = K8sResourceCpuMem()
    limits: K8sResourceCpuMem = K8sResourceCpuMem()


class K8sSecurityContext(BaseModel):
    runAsUser: int
    capabilities: List[str]


class K8sEnvVar(BaseModel):
    name: str
    value: str = ""
    valueFrom: Any = None


class K8sContainer(BaseModel):
    name: str = ""
    image: str = ""
    command: List[str] = []
    args: List[str] = []
    env: List[K8sEnvVar] = []
    ports: List[dict] = []
    resources: K8sRequestLimit = K8sRequestLimit()
    livenessProbe: K8sProbe = K8sProbe()
    readinessProbe: K8sProbe = K8sProbe()
    imagePullPolicy: Any = None
    securityContext: dict = {}
    terminationMessagePath: Any = None
    terminationMessagePolicy: Any = None


class K8sPodSpec(BaseModel):
    containers: List[K8sContainer] = []
    restartPolicy: str = ""
    serviceAccountName: str = ""
    affinity: dict = {}
    tolerations: List[dict] = []
    schedulerName: Any = None
    securityContext: Any = None
    terminationGracePeriodSeconds: Any = None
    dnsPolicy: Any = None


class K8sPodStatusCondition(BaseModel):
    type: str = ""
    status: str = ""
    reason: str = ""
    message: str = ""


class K8sPodStatusContainer(BaseModel):
    name: str = ""
    ready: bool = False
    restartCount: int = 0
    state: dict = {}


class K8sPodStatus(BaseModel):
    phase: str = ""
    conditions: List[K8sPodStatusCondition] = []
    containerStatuses: List[K8sPodStatusContainer] = []
    startTime: str = ""


class K8sPod(BaseModel):
    apiVersion: str = ""
    kind: str = ""
    metadata: K8sMetadata = K8sMetadata()
    spec: K8sPodSpec = K8sPodSpec()
    status: K8sPodStatus = K8sPodStatus()


class K8sDeploymentSpec(BaseModel):
    replicas: int = 0
    selector: dict
    template: K8sPod
    progressDeadlineSeconds: int = -1
    revisionHistoryLimit: int = -1
    strategy: Any = None


class K8sDeployment(BaseModel):
    apiVersion: str = ""
    kind: str = ""
    metadata: K8sMetadata
    spec: K8sDeploymentSpec


# ----------------------------------------------------------------------
# DFH Internal Models.
# ----------------------------------------------------------------------


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    kubeconfig: Path
    kubecontext: str

    # Only track resources with this `apps.kubernetes.io/managed-by` value.
    managed_by: str

    # Group applications by environment based on this label.
    env_label: str

    loglevel: str
    host: str
    port: int

    # A single reusable HTTP client for the entire app.
    httpclient: httpx.AsyncClient


class DeploymentInfo(BaseModel):
    """User configurable values for a deployment."""

    model_config = ConfigDict(extra="forbid")

    isFlux: bool = False
    resources: K8sRequestLimit = K8sRequestLimit()
    useResources: bool = False
    livenessProbe: K8sProbe = K8sProbe()
    useLivenessProbe: bool = False
    readinessProbe: K8sProbe = K8sProbe()
    useReadinessProbe: bool = False
    envVars: List[K8sEnvVar] = []
    secrets: List[KeyValue] = []
    image: str = ""
    name: str = ""
    command: str = ""
    args: str = ""


class WatchedResource(BaseModel):
    """Each watch uses one instance of this to track the resource it monitors."""

    model_config = ConfigDict(extra="forbid")

    apiVersion: str
    kind: str
    path: str
    manifests: Dict[str, dict] = {}


def factory_WatchedResource() -> Dict[str, WatchedResource]:
    """Aggregate all the monitored resources["

    There is one `Watch` instance for each resource.
    """
    data = dict(
        Namespace=WatchedResource(
            kind="Namespace", apiVersion="v1", path="/api/v1/namespaces"
        ),
        Pod=WatchedResource(kind="Pod", apiVersion="v1", path="/api/v1/pods"),
        Service=WatchedResource(
            kind="Service", apiVersion="v1", path="/api/v1/services"
        ),
        Deployment=WatchedResource(
            kind="Deployment", apiVersion="apps/v1", path="/apis/apps/v1/deployments"
        ),
        VirtualService=WatchedResource(
            apiVersion="networking.istio.io/v1beta1",
            kind="VirtualService",
            path="/apis/networking.istio.io/v1beta1/virtualservices",
        ),
        DestinationRule=WatchedResource(
            apiVersion="networking.istio.io/v1beta1",
            kind="DestinationRule",
            path="/apis/networking.istio.io/v1beta1/destinationrules",
        ),
    )
    return data


class AppService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = 0
    targetPort: int = 0


class AppHpa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""


class AppMetadata(BaseModel):
    """Generic information about the app. Not to be confused with the K8s Metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    env: str = ""
    namespace: str = ""


class AppPrimary(BaseModel):
    """Captures all the K8s resources of the primary."""

    model_config = ConfigDict(extra="forbid")

    deployment: DeploymentInfo = DeploymentInfo()
    hpa: AppHpa = AppHpa()
    service: AppService = AppService()
    useService: bool = False


class AppCanary(BaseModel):
    """Captures all the K8s resources of the canary."""

    model_config = ConfigDict(extra="forbid")

    deployment: DeploymentInfo = DeploymentInfo()
    hpa: AppHpa = AppHpa()
    service: AppService = AppService()
    useService: bool = False
    trafficPercent: int = 0


# ----------------------------------------------------------------------
# API Interface Models.
# ----------------------------------------------------------------------


class AppInfo(BaseModel):
    """GET/POST/PATCH /api/crt/v1/apps/{name}/{env}"""

    model_config = ConfigDict(extra="forbid")

    metadata: AppMetadata = AppMetadata()
    primary: AppPrimary = AppPrimary()
    canary: AppCanary = AppCanary()
    hasCanary: bool = False


class PodList(BaseModel):
    """GET /api/crt/v1/pods"""

    model_config = ConfigDict(extra="forbid")

    class PodInfo(BaseModel):
        id: str = ""
        name: str = ""
        namespace: str = ""
        ready: str = ""
        restarts: int = 0
        age: str = ""
        phase: str = ""
        message: str = ""
        reason: str = ""

    items: List[PodInfo] = []


class JobStatus(BaseModel):
    """GET `/api/crt/v1/jobs/{jobId}`"""

    model_config = ConfigDict(extra="forbid")

    jobId: str
    logs: List[str]
    done: bool


class JobDescription(BaseModel):
    """POST `/api/crt/v1/jobs`"""

    model_config = ConfigDict(extra="forbid")

    jobId: str


class AppEnvOverview(BaseModel):
    """GET /api/crt/v1/apps"""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    envs: List[str]


# ----------------------------------------------------------------------
# Database modelling.
# ----------------------------------------------------------------------
class DatabaseAppEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appInfo: AppInfo
    resources: Dict[str, WatchedResource] = factory_WatchedResource()


class Database(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # appInfo[appname][env], eg appInfo['nginx']['stg']
    apps: Dict[str, Dict[str, DatabaseAppEntry]] = {}

    # All tracked K8s resources. Those may or may not be part of an app.
    resources: Dict[str, WatchedResource] = factory_WatchedResource()


class GeneratedManifests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources: Dict[str, WatchedResource] = factory_WatchedResource()


# ----------------------------------------------------------------------
# User Access Management.
# ----------------------------------------------------------------------


class GoogleToken(BaseModel):
    token: str


class UAMUser(BaseModel):
    email: str = Field(pattern=r"^[a-z]+['a-z0-9_.+-]*@[a-z0-9-]+\.[a-z0-9-.]+$")  # uid
    name: str
    lanid: str
    slack: str
    role: str
    manager: str

    @field_validator("name", "lanid", "slack")
    @classmethod
    def valid_name(cls, v: str) -> str:
        if len(v) != len(v.strip()):
            raise ValueError("must not have leading or trailing whitespace")

        if len(v) == 0:
            raise ValueError("must be nonempty")
        return v


class UAMGroup(BaseModel):
    name: str  # uid
    owner: str
    provider: str
    description: str = ""
    users: Dict[str, UAMUser] = Field(default_factory=dict)
    children: Dict[str, "UAMGroup"] = Field(default_factory=dict)

    @field_validator("name", "owner")
    @classmethod
    def valid_name(cls, v: str) -> str:
        if len(v) != len(v.strip()):
            raise ValueError("must not have leading or trailing whitespace")

        if len(v) == 0:
            raise ValueError("must be nonempty")
        return v


class UAMTreeNode(BaseModel):
    id: str
    label: str
    elId: str
    children: List["UAMTreeNode"] | None = None


class UAMDatabase(BaseModel):
    users: Dict[str, UAMUser]
    groups: Dict[str, UAMGroup]
    root: UAMGroup = UAMGroup(name="Org", owner="none", provider="none")


class UAMChild(BaseModel):
    child: str
