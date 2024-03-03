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
