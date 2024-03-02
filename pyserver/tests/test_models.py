import json
from pathlib import Path

import yaml

import dfh.models
from dfh.manifest_utilities import is_dfh_manifest
from dfh.models import (
    K8sDestinationRule,
    K8sPod,
    K8sService,
    K8sVirtualService,
)

# Convenience: we can re-use it in all tests.
from .conftest import get_server_config

cfg = get_server_config()


class TestModels:
    def test_K8sService(self):
        raw = yaml.safe_load(Path("tests/support/service_specimen.yaml").read_text())
        assert is_dfh_manifest(cfg, raw)
        model = K8sService.model_validate(raw)
        assert is_dfh_manifest(cfg, model.model_dump())

        assert model.metadata.name == "demoapp-stg"
        assert model.metadata.namespace == "default"
        assert model.apiVersion == "v1"
        assert model.kind == "Service"
        assert len(model.spec.ports) == 1
        assert model.spec.ports[0].model_dump() == {
            "name": "http",
            "port": 80,
            "protocol": "TCP",
            "appProtocol": "TCP",
            "targetPort": 80,
        }

        assert model.spec.selector == {
            "app": "demoapp",
            "env": "stg",
        }

    def test_factory_WatchedResource(self):
        resources = dfh.models.factory_WatchedResource()
        assert set(resources.keys()) == {
            "Namespace",
            "Pod",
            "Service",
            "Deployment",
            "ClusterRole",
            "VirtualService",
            "DestinationRule",
        }

        for name, res in resources.items():
            assert res.kind == name

    def test_virtualservice(self):
        raw = yaml.safe_load(
            Path("tests/support/virtualservice-specimen.yaml").read_text()
        )
        assert is_dfh_manifest(cfg, raw)
        model = K8sVirtualService.model_validate(raw)
        assert model.kind == "VirtualService"
        assert model.apiVersion == "networking.istio.io/v1beta1"

        assert is_dfh_manifest(cfg, model.model_dump())
        assert raw["spec"] == model.spec.model_dump()

    def test_destinationrule(self):
        raw = yaml.safe_load(
            Path("tests/support/destinationrule-specimen.yaml").read_text()
        )
        assert is_dfh_manifest(cfg, raw)
        model = K8sDestinationRule.model_validate(raw)
        assert model.kind == "DestinationRule"
        assert model.apiVersion == "networking.istio.io/v1beta1"

        assert is_dfh_manifest(cfg, model.model_dump())
        assert raw["spec"] == model.spec.model_dump()

    def test_pod(self):
        """Must be able to reproduce the salient parts of a Pod.

        We care in particular about the environment variables here because they
        can have two possible formats.
        """
        raw = yaml.safe_load(Path("tests/support/pod.yaml").read_text())
        assert is_dfh_manifest(cfg, raw)
        model = K8sPod.model_validate(raw)

        assert is_dfh_manifest(cfg, model.model_dump())
        out = model.model_dump(exclude_defaults=True)
        env_vars = out["spec"]["containers"][0]["env"]
        assert len(env_vars) == 2
        assert env_vars[0] == dict(name="foo", value="bar")
        assert env_vars[1] == dict(
            name="from-label",
            valueFrom={
                "fieldRef": dict(
                    apiVersion="v1",
                    fieldPath="metadata.uid",
                )
            },
        )
