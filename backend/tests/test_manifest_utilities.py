from dfh.manifest_utilities import is_dfh_manifest

from .conftest import get_server_config

cfg = get_server_config()


class TestBasic:
    def test_is_dfh_manifest(self):
        # Invalid.
        assert not is_dfh_manifest(cfg, {})
        assert not is_dfh_manifest(cfg, {"metadata": {}})
        assert not is_dfh_manifest(cfg, {"metadata": {"labels": {}}})

        # Invalid because the values must be non-empty.
        manifest = {
            "metadata": {
                "labels": {
                    cfg.env_label: "",
                    "app.kubernetes.io/name": "",
                    "app.kubernetes.io/managed-by": cfg.managed_by,
                }
            }
        }
        assert not is_dfh_manifest(cfg, manifest)

        # Invalid because it is not managed by DFH.
        manifest = {
            "metadata": {
                "labels": {
                    cfg.env_label: "stg",
                    "app.kubernetes.io/name": "name",
                    "app.kubernetes.io/managed-by": "someone else",
                }
            }
        }
        assert not is_dfh_manifest(cfg, manifest)

        # Valid.
        manifest = {
            "metadata": {
                "labels": {
                    cfg.env_label: "stg",
                    "app.kubernetes.io/name": "name",
                    "app.kubernetes.io/managed-by": cfg.managed_by,
                }
            }
        }
        assert is_dfh_manifest(cfg, manifest)
