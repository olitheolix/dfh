"""Replicate Square types with Pydantic models."""

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class MetaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """Minimum amount of information to uniquely identify a K8s resource.

    The primary purpose of this tuple is to provide an immutable UUID that
    we can use as keys in dictionaries and sets.

    """
    apiVersion: str
    kind: str
    namespace: str | None

    # Every resource must have a name except for Namespaces, which encode their
    # name in the `namespace` field.
    name: str | None


class DeltaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: MetaManifest
    url: str
    manifest: Dict[str, Any]


class DeltaDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: MetaManifest
    url: str
    manifest: Dict[str, Any]


class DeltaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: MetaManifest
    diff: str


class DeploymentPlan(BaseModel):
    """Describe Square plan.

    Collects all resources manifests to add/delete as well as the JSON
    patches that make up a full plan.

    """

    jobId: str
    create: List[DeltaCreate]
    patch: List[DeltaPatch]
    delete: List[DeltaDelete]
