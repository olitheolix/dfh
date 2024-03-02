// ----------------------------------------------------------------------
// API Payloads
// ----------------------------------------------------------------------
export interface KeyValuePairType {
    key: string;
    value: string;
}

export interface AppService {
    port: number
    targetPort: number
}

export interface AppHpa {
    name: string
}

export interface K8sResourceCpuMem {
    cpu: string
    memory: string

}

export interface K8sRequestLimit {
    requests: K8sResourceCpuMem
    limits: K8sResourceCpuMem
}

export interface K8sProbeHttp {
    path: string
    port: number
}

export interface K8sProbe {
    httpGet: K8sProbeHttp
    initialDelaySeconds: number
    periodSeconds: number
}

export interface DeploymentInfo {
    isFlux: boolean
    resources: K8sRequestLimit
    useResources: boolean
    livenessProbe: K8sProbe
    useLivenessProbe: boolean
    readinessProbe: K8sProbe
    useReadinessProbe: boolean
    envVars: KeyValuePairType[]
    secrets: KeyValuePairType[]
    image: string
    name: string
}

export interface AppMetadata {
    name: string
    env: string
    namespace: string
}

export interface AppPrimary {
    deployment: DeploymentInfo
    hpa: AppHpa
    service: AppService
    useService: boolean
}

export interface AppCanary {
    deployment: DeploymentInfo
    hpa: AppHpa
    service: AppService
    trafficPercent: number
    useService: boolean
}

export interface AppSpec {
    metadata: AppMetadata
    primary: AppPrimary
    canary: AppCanary
    hasCanary: boolean
}

export interface PodInfo {
    id: string
    name: string
    namespace: string
    ready: string
    restarts: number
    age: string
    phase: string
    message: string
    reason: string
}

export interface PodList {
    items: PodInfo[]
}

export interface AppEnvOverview {
    id: string
    name: string
    envs: string[]
}

export interface JobStatus {
    jobId: number
    logs: string[]
    done: boolean
}

// ----------------------------------------------------------------------
// Square specific types to show a plan.
// ----------------------------------------------------------------------
export interface MetaManifest {
    apiVersion: string
    kind: string
    namespace: string | null
    name: string | null
}

export interface DeltaCreate {
    meta: MetaManifest
    url: string
    manifest: any
}

export interface DeltaDelete {
    meta: MetaManifest
    url: string
    manifest: any
}

export interface DeltaPatch {
    meta: MetaManifest
    diff: string
}

export interface DeploymentPlan {
    jobId: number
    create: DeltaCreate[]
    patch: DeltaPatch[]
    delete: DeltaDelete[]
}
