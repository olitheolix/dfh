import yaml

import dfh.defaults


class TestDefaults:
    def test_pod_fieldref_envs(self):
        out = dfh.defaults.pod_fieldref_envs()

        names = [_.name for _ in out]
        assert len(names) == 5
        assert set(names) == set(dfh.defaults.RESERVED_FIELDREF_ENVS)

    def test_security_context(self):
        # Nothing much to test here so we just verify that it executes.
        ctx = dfh.defaults.pod_security_context()
        assert isinstance(ctx, dict)

    def test_topology_spread(self):
        ts = dfh.defaults.topology_spread({"app": "foo"})
        assert len(ts) == 2
        assert ts[0]["topologyKey"] == "topology.kubernetes.io/zone"
        assert ts[1]["topologyKey"] == "kubernetes.io/hostname"

        # Ensure the dumped YAML does not contain any anchor tags. This
        # typically happens when we reuse an object like, in our case the
        # `{app: foo}` dict when we called the function. This is harmless for
        # K8s and valid YAML but it creates annoying diffs. The
        # `topology_spread` function must therefore ensure it uses copies
        # instead of references.
        assert "&id" not in yaml.dump(ts)
