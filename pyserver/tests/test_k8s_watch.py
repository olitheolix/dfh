import asyncio
import json
import logging
from pathlib import Path
from typing import Dict
from unittest import mock

import httpx
import pytest
import respx
import yaml
from httpx import Response
from square.dtypes import K8sConfig

import dfh.generate
import dfh.watch
from dfh.manifest_utilities import is_dfh_manifest
from dfh.models import (
    AppInfo,
    AppMetadata,
    AppPrimary,
    Database,
    DeploymentInfo,
)

from .conftest import get_server_config

# Convenience: we can re-use it in all tests.
cfg = get_server_config()


class TestBasic:
    def test_createClusterConfig(self, tmp_path: Path):
        # Kubeconfig does not exists.
        _, err = dfh.watch.create_cluster_config(Path("/does/not/exist"), "")
        assert err

        # Valid Kubeconfig.
        kubeconf = Path("tests/support/valid_kubeconf.yaml")
        _, err = dfh.watch.create_cluster_config(kubeconf, "kind-kind")
        assert not err

        # Corrupt the valid Kubeconfig to force the SSL error.
        kubeconf = yaml.safe_load(kubeconf.read_text())
        user = kubeconf["users"][0]["user"]
        user["client-key-data"] = ""
        kubeconf2 = tmp_path / "kubeconf.yaml"
        kubeconf2.write_text(yaml.dump(kubeconf))

        _, err = dfh.watch.create_cluster_config(kubeconf2, "kind-kind")
        assert err


class TestWatchMockedBackgroundTask:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Replace the list of tasks with a list of a single mock."""
        with mock.patch.object(dfh.watch.WatchResource, "start_tasks") as m:
            m.return_value = [mock.AsyncMock()]
            yield

    async def test_ctor(self, k8scfg: K8sConfig):
        path = "/api/crt/v1/namespaces"
        client = k8scfg.client

        # Default values.
        watch = dfh.watch.WatchResource(client, path)
        assert watch.client == client
        assert watch.last_rv == -1
        assert watch.queue.qsize() == 0
        assert watch.list_path == path
        assert watch.watch_path == f"/api/crt/v1/namespaces?watch=true&timeoutSeconds=5"
        assert watch.logit == logging.getLogger("Watch")
        assert len(watch.tasks) == 1

        # Custom values.
        custom_logger = logging.getLogger("default")
        watch = dfh.watch.WatchResource(
            client, path, rv=10, timeout=20, logger=custom_logger
        )
        assert watch.client == client
        assert watch.last_rv == 10
        assert watch.queue.qsize() == 0
        assert watch.list_path == path
        assert (
            watch.watch_path == f"/api/crt/v1/namespaces?watch=true&timeoutSeconds=20"
        )
        assert watch.logit == custom_logger
        assert len(watch.tasks) == 1

    async def test_get_logging_metadata(self):
        """Basic test to validate the logging metadata."""
        path = "/api/crt/v1/namespaces"

        # Session without explicit host.
        async with httpx.AsyncClient() as client:
            watch = dfh.watch.WatchResource(client, path)
            ret = watch.get_logging_metadata()
            assert ret == {
                "component": "k8s-watch",
                "path": path,
                "host": "",
            }

        # Session with explicit host.
        async with httpx.AsyncClient(base_url="http://10.1.2.3:8080") as client:
            watch = dfh.watch.WatchResource(client, path)
            ret = watch.get_logging_metadata()
            assert ret == {
                "component": "k8s-watch",
                "path": path,
                "host": "http://10.1.2.3:8080",
            }

    async def test_context_manager(self, k8scfg: K8sConfig):
        """Context manager must `cancel` all tasks."""
        path = "/api/crt/v1/namespaces"

        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert not watch.tasks[0].cancel.called
        async with watch:
            pass
        assert watch.tasks[0].cancel.called

    async def test_WatchResource_iterator_basic(self, k8scfg: K8sConfig):
        """The class must yield the content of the queue."""
        path = "/api/crt/v1/namespaces"

        watch = dfh.watch.WatchResource(k8scfg.client, path)

        # Pretend K8s sent us one line before the task was cancelled.
        await watch.queue.put("k8s-line-1")
        await watch.queue.put("__CANCELLED__")
        data = [_ async for _ in watch]
        assert data == ["k8s-line-1"]

        # Pretend K8s sent us one line before the task raised an unhandled exception.
        await watch.queue.put("k8s-line-2")
        await watch.queue.put("__EXCEPTION__")
        data = [_ async for _ in watch]
        assert data == ["k8s-line-2"]

    async def test_list_resources_ok(self, k8scfg: K8sConfig):
        """Must return the correct resource version from a LIST operation."""
        # Important: K8s returns the resourceVersion as a string, not an integer.
        uid = 50
        obj = {"metadata": {"uid": uid}}
        manifest = {"metadata": {"resourceVersion": "5"}, "items": [obj]}
        path = "/api/crt/v1/namespaces"

        # Mock the K8s request to return our dummy manifests.
        m_http = respx.get(path)
        m_http.return_value = Response(200, json=manifest)

        # Function must return the resource version as an *integer*. This
        # is because K8s encodes the resource version as a string.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.state == {}
        ret = await watch.list_resource()
        assert watch.state == {uid: obj}
        assert watch.queue.qsize() == 1
        assert ret == (5, False)

    async def test_list_resources_err(self, k8scfg: K8sConfig):
        """Must gracefully handle errors during the LIST operation."""
        path = "/does/not/exist"

        # Pretend the server responds with 404.
        m_http = respx.get(path)
        m_http.return_value = Response(404, json={})

        # The `list_resource` method must return with an error.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert await watch.list_resource() == (-1, True)

    async def test_update_state_inconsistent(self, k8scfg: K8sConfig):
        """`update_state` must be able to copy with non-existing UIDs.

        Here we ask the function to modify and remove two resources that are
        not tracked as part of the state. While this is almost certainly a bug
        the function must still be able function.

        """
        path = "/api/crt/v1/namespaces"
        rv1, rv2 = 30, 40
        uid1, uid2 = "1", "2"

        # Simulate K8s sending three lines followed by an empty one to signify
        # that the connection is now closed.
        obj1 = {"metadata": {"resourceVersion": str(rv1), "uid": uid1}}
        obj2 = {"metadata": {"resourceVersion": str(rv2), "uid": uid2}}
        line_mod_1 = {"type": "MODIFIED", "object": obj1}
        line_del_2 = {"type": "DELETED", "object": obj2}
        line_add_1 = {"type": "ADDED", "object": obj1}

        # Create the `WatchResource` instance and ensure it reads the lines
        # and puts them into the queue before returning successfully.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.state == {}
        assert watch.last_rv == -1
        assert watch.queue.qsize() == 0

        # Modify the non-existing `obj1`. The function must add the
        # corresponding UID to the state and emit an ADDED event because as
        # far as this class is concerned the resource is new.
        await watch.update_state(line_mod_1)
        assert watch.last_rv == rv1
        assert watch.state == {uid1: obj1}
        assert watch.queue.qsize() == 1
        event = await watch.queue.get()
        assert event["type"] == "ADDED"

        # Delete the non-existing `obj1`. The function must silently ignore
        # the event and not queue any events.
        await watch.update_state(line_del_2)
        assert watch.last_rv == rv2
        assert watch.state == {uid1: obj1}
        assert watch.queue.qsize() == 0

        # Add the already `obj1` a second time. The function must treat
        # this as a MODIFIED event.
        await watch.update_state(line_add_1)
        assert watch.last_rv == rv1
        assert watch.state == {uid1: obj1}
        assert watch.queue.qsize() == 1
        event = await watch.queue.get()
        assert event["type"] == "MODIFIED"

    async def test_update_state(self, k8scfg: K8sConfig):
        """Pass ADDED, MODIFIED and DELETED events and verify the state."""
        path = "/api/crt/v1/namespaces"
        uid1 = "1"

        # Simulate K8s sending three lines followed by an empty one to signify
        # that the connection is now closed.
        line_add = {"object": {"metadata": {"uid": uid1}}, "type": "ADDED"}
        line_mod = {"object": {"metadata": {"uid": uid1}}, "type": "MODIFIED"}
        line_del = {"object": {"metadata": {"uid": uid1}}, "type": "DELETED"}
        line_add["object"]["metadata"]["resourceVersion"] = "1"  # type: ignore
        line_mod["object"]["metadata"]["resourceVersion"] = "2"  # type: ignore
        line_del["object"]["metadata"]["resourceVersion"] = "3"  # type: ignore

        # Create the `WatchResource` instance and ensure it reads the lines
        # and puts them into the queue before returning successfully.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.state == {}
        assert watch.last_rv == -1
        assert watch.queue.qsize() == 0

        # Add a new object.
        await watch.update_state(line_add)
        assert watch.last_rv == 1
        assert watch.state == {uid1: line_add["object"]}
        assert watch.queue.qsize() == 1
        event = await watch.queue.get()
        assert event["type"] == "ADDED"

        # Modify the existing object.
        await watch.update_state(line_mod)
        assert watch.last_rv == 2
        assert watch.state == {uid1: line_mod["object"]}
        assert watch.queue.qsize() == 1
        event = await watch.queue.get()
        assert event["type"] == "MODIFIED"

        # Delete the object.
        await watch.update_state(line_del)
        assert watch.last_rv == 3
        assert watch.state == {}
        assert watch.queue.qsize() == 1
        event = await watch.queue.get()
        assert event["type"] == "DELETED"

    async def test_parse_line_ok(self, k8scfg: K8sConfig):
        """Use valid K8s events to very the line processing."""
        path = "/api/crt/v1/namespaces"
        rv1, uid1 = 30, "1"

        # Simulate a valid payload from a K8s watch stream.
        obj1 = {"metadata": {"resourceVersion": str(rv1), "uid": uid1}}
        line = json.dumps({"type": "ADDED", "object": obj1})

        # Setup Watch.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.state == {}
        assert watch.last_rv == -1

        # Function must do nothing if the line is empty. Empty lines are
        # harmless and signify that K8s has closed the connection.
        assert await watch.parse_line("") is False
        assert watch.last_rv == -1

        # Use a valid K8s event and verify that the function updated the
        # value of `last_rv`, the internal state and queued an ADDED event.
        assert await watch.parse_line(line) is False
        assert watch.last_rv == rv1
        assert watch.state == {uid1: obj1}
        assert watch.queue.qsize() == 1
        ret = await watch.queue.get()
        assert ret["type"] == "ADDED"

    @pytest.mark.parametrize("is_410", [True, False])
    async def test_parse_line_k8s_err(self, is_410: bool, k8scfg: K8sConfig):
        """Must be able to handle error manifests.

        K8s will send ERROR events from time to time. This is expected and
        the function must be able to process them and return an error. The only
        exception is a 410 error since that one is expected and does not
        constitute an error for us because all it means is that we should
        resume the watch immediately.

        """
        path = "/api/crt/v1/namespaces"
        line = json.dumps(
            {
                "type": "ERROR",
                "object": {
                    "apiVersion": "v1",
                    "code": 410 if is_410 else 420,
                    "kind": "Status",
                    "message": "too old resource version: 11498 (39652)",
                    "metadata": {},
                    "reason": "Expired",
                    "status": "Failure",
                },
            }
        )

        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.last_rv == -1

        # All errors except 410 must signal an error.
        ret = await watch.parse_line(line)
        assert ret is False if is_410 else True
        assert watch.last_rv == -1
        assert watch.queue.qsize() == 0

    async def test_parse_line_json_err(self, k8scfg: K8sConfig):
        """Gracefully abort if we receive a corrupt JSON line."""
        path = "/api/crt/v1/namespaces"

        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.last_rv == -1

        # Must return with an error and not do anything else.
        assert await watch.parse_line("{invalid json]") is True
        assert watch.last_rv == -1
        assert watch.state == {}
        assert watch.queue.qsize() == 0

    @pytest.mark.parametrize("status", [200, 404])
    @pytest.mark.parametrize("initial_rv", [10, -10])
    @mock.patch.object(dfh.watch.WatchResource, "parse_line")
    @mock.patch.object(dfh.watch.WatchResource, "list_resource")
    async def test_read_k8s_stream_restart(
        self, m_list, m_parse, initial_rv: int, status: bool, k8scfg: K8sConfig
    ):
        """Simulate watch restart because resource version was negative."""
        path, rv = "/api/crt/v1/namespaces", 10

        watch = dfh.watch.WatchResource(k8scfg.client, path, rv=rv)
        watch.last_rv = initial_rv
        m_list.return_value = (10, status != 200)

        # Setup a mock to return a multi-line text response.
        m_http = respx.get(watch.construct_watch_path(rv))
        m_http.return_value = Response(status, text="line1\nline2")

        # Consume the stream and verify the function processes the events.
        ret = await watch.read_k8s_stream()
        if status == 200:
            # Must have passed both messages to `parse_line`.
            assert ret is False and m_parse.call_count == 2
        else:
            # Must return with an error not have parsed any messages.
            assert ret is True and m_parse.call_count == 0

    async def test_read_k8s_stream_list_error(self, k8scfg: K8sConfig):
        """Gracefully abort if LIST operations fails."""
        path = "/api/crt/v1/namespaces"

        m_http = respx.get(path)
        m_http.return_value = Response(404, json={})

        # Create watch.
        watch = dfh.watch.WatchResource(k8scfg.client, path)
        assert watch.last_rv == -1

        # Stream reader must return with an error and not update the latest
        # resource version.
        assert await watch.read_k8s_stream() is True
        assert watch.last_rv == -1
        assert watch.queue.qsize() == 0

    @mock.patch.object(dfh.watch.WatchResource, "read_k8s_stream")
    @mock.patch.object(dfh.watch.asyncio, "sleep")
    async def test_background_runner_loop(self, m_sleep, m_bgs, k8scfg: K8sConfig):
        """Runner must restart the `read_k8s_stream`.

        If `read_k8s_stream` returns an error it must wait 30s before
        it tries again.

        """
        path = "/api/crt/v1/namespaces"

        # The background function must raise the unhandled exception but only
        # after it queued the __CANCELLED__ message.
        m_bgs.side_effect = [False, True, asyncio.CancelledError]

        watch = dfh.watch.WatchResource(k8scfg.client, path, rv=-1)
        await watch.background_runner()
        m_sleep.assert_called_once_with(30)

    @mock.patch.object(dfh.watch.WatchResource, "read_k8s_stream")
    async def test_background_runner_cancelled(self, m_bgs, k8scfg: K8sConfig):
        """Runner task must emit __CANCELLED__ and shut down cleanly."""
        path = "/api/crt/v1/namespaces"

        # The background function must raise the unhandled exception but only
        # after it queued the __CANCELLED__ message.
        m_bgs.side_effect = asyncio.CancelledError

        watch = dfh.watch.WatchResource(k8scfg.client, path, rv=-1)
        await watch.background_runner()
        assert await watch.queue.get() == "__CANCELLED__"
        assert watch.queue.qsize() == 0

    @mock.patch.object(dfh.watch.WatchResource, "read_k8s_stream")
    async def test_background_runner_unhandled_exception(
        self, m_bgs, k8scfg: K8sConfig
    ):
        """Runner task must emit __EXCEPTION__ and shut down cleanly."""
        path = "/api/crt/v1/namespaces"

        # Pretend the background task aborted with an exception.
        m_bgs.side_effect = ValueError

        # The background function must raise the unhandled exception but only
        # after it queued the __EXCEPTION__ message.
        watch = dfh.watch.WatchResource(k8scfg.client, path, rv=-1)

        try:
            await watch.background_runner()
            assert False
        except ValueError:
            pass
        assert await watch.queue.get() == "__EXCEPTION__"
        assert watch.queue.qsize() == 0

    async def test_reset_state_no_op(self, k8scfg: K8sConfig):
        """The old state matches the new state."""
        path = "/api/crt/v1/namespaces"
        watch = dfh.watch.WatchResource(k8scfg.client, path)

        # No existing state and no new manifests. This must do nothing.
        state: Dict[str, dict] = {}
        await watch.reset_state([], state)
        assert state == {} and watch.queue.qsize() == 0

        # Existing state matches the new manifest.
        obj = {"metadata": {"uid": "1"}}
        state = {"1": obj}
        await watch.reset_state([obj], state)
        assert state == {"1": obj} and watch.queue.qsize() == 0

    async def test_reset_state_add(self, k8scfg: K8sConfig):
        """Add new objects to the state."""
        path = "/api/crt/v1/namespaces"

        watch = dfh.watch.WatchResource(k8scfg.client, path)

        # Must add one document to the state and fake the corresponding event.
        state: Dict[str, dict] = {}
        obj = {"metadata": {"uid": "1"}}
        await watch.reset_state([obj], state)
        assert state == {"1": obj}
        assert watch.queue.qsize() == 1
        assert await watch.queue.get() == {"type": "ADDED", "object": obj}

    async def test_reset_state_modified(self, k8scfg: K8sConfig):
        """Patch existing objects in the state."""
        path = "/api/crt/v1/namespaces"

        # Same object but different content. Function must update the state
        # and emit the corresponding MODIFIED event.
        obj1_a = {"metadata": {"uid": "1", "foo": "bar_a"}}
        obj1_b = {"metadata": {"uid": "1", "foo": "bar_b"}}

        watch = dfh.watch.WatchResource(k8scfg.client, path)

        # Same object but different content. Function must update the state
        # and emit the corresponding MODIFIED event.
        state = {"1": obj1_a}
        await watch.reset_state([obj1_b], state)
        assert state == {"1": obj1_b}

        assert watch.queue.qsize() == 1
        assert await watch.queue.get() == {"type": "MODIFIED", "object": obj1_b}

    async def test_reset_state_delete(self, k8scfg: K8sConfig):
        """Add new objects to the state."""
        path = "/api/crt/v1/namespaces"

        # Same object but different content. Function must update the state
        # and emit the corresponding DELETED event.
        obj1_a = {"metadata": {"uid": "1", "foo": "bar_a"}}
        obj2_a = {"metadata": {"uid": "2", "foo": "bar_a"}}

        watch = dfh.watch.WatchResource(k8scfg.client, path)

        state = {"1": obj1_a, "2": obj2_a}
        await watch.reset_state([obj1_a], state)
        assert state == {"1": obj1_a}
        assert watch.queue.qsize() == 1
        assert await watch.queue.get() == {"type": "DELETED", "object": obj2_a}

    async def test_reset_state_mixed(self, k8scfg: K8sConfig):
        """Add, remove and modify objects in the state."""
        path = "/api/crt/v1/namespaces"

        # Dummy manifests.
        obj1_a = {"metadata": {"uid": "1", "foo": "bar_a"}}
        obj2_a = {"metadata": {"uid": "2", "foo": "bar_a"}}
        obj2_b = {"metadata": {"uid": "2", "foo": "bar_b"}}
        obj3_a = {"metadata": {"uid": "3", "foo": "bar_a"}}
        obj4_b = {"metadata": {"uid": "4", "foo": "bar_b"}}

        watch = dfh.watch.WatchResource(k8scfg.client, path)

        # Current state knows of three objects but the new manifests add,
        # remove and modify one.
        state = {"1": obj1_a, "2": obj2_b, "3": obj3_a}
        await watch.reset_state([obj1_a, obj2_a, obj4_b], state)
        assert state == {"1": obj1_a, "2": obj2_a, "4": obj4_b}

        assert watch.queue.qsize() == 3
        assert await watch.queue.get() == {"type": "DELETED", "object": obj3_a}
        assert await watch.queue.get() == {"type": "ADDED", "object": obj4_b}
        assert await watch.queue.get() == {"type": "MODIFIED", "object": obj2_a}


class TestWatchWithBackgroundTask:
    @mock.patch.object(dfh.watch.WatchResource, "read_k8s_stream")
    async def test_background_runner(self, m_bgs, k8scfg: K8sConfig):
        """Ensure that `WatchResource` actually starts the runner.

        To verify that, we will instantiate `WatchResource` with a mocked
        `read_k8s_stream` that immediately raises a `CancelledError`.
        If everything works as expected then the iterator must return without
        yielding any results.

        """
        path = "/api/crt/v1/namespaces"

        m_bgs.side_effect = asyncio.CancelledError

        watch = dfh.watch.WatchResource(k8scfg.client, path, rv=-1)
        results = [_ async for _ in watch]
        assert len(results) == 0


class TestResourceTracking:
    def test_upsert_resource(self):
        db: Database = Database()
        gen = dfh.generate

        # Must silently ignore invalid manifests.
        dfh.watch.upsert_resource(cfg, db, {})
        assert db == Database()

        # Generate test manifests.
        manifests = {}
        app_infos = {}
        for name in ("demo-1", "demo-2"):
            app_infos[name] = {}
            for env in ("stg", "prod"):
                ns = f"ns-{env}"
                app_infos[name][env] = AppInfo(
                    metadata=AppMetadata(name=name, env=env, namespace=ns),
                    primary=AppPrimary(
                        deployment=DeploymentInfo(
                            image=f"{name}:{env}",
                        )
                    ),
                )
                data, err = gen.manifests_from_appinfo(
                    cfg, app_infos[name][env], Database()
                )
                assert not err

                key = gen.watch_key(app_infos[name][env].metadata, False)
                manifest = data.resources["Deployment"].manifests[key]
                manifests[(name, env)] = manifest
                assert is_dfh_manifest(cfg, manifest)
                del data, key, manifest
        del ns

        # Add the test manifests.
        for (name, env), manifest in manifests.items():
            dfh.watch.upsert_resource(cfg, db, manifest)

        # Verify that all manifests exist and are correct.
        for (name, env), manifest in manifests.items():
            key = gen.watch_key(app_infos[name][env].metadata, False)
            assert db.resources["Deployment"].manifests[key] == manifest

        # Remove one manifest at a time.
        dfh.watch.remove_resource(cfg, db, manifests[("demo-1", "stg")])
        cur_keys = set(db.resources["Deployment"].manifests.keys())
        assert cur_keys == {
            gen.watch_key(app_infos["demo-1"]["prod"].metadata, False),
            gen.watch_key(app_infos["demo-2"]["stg"].metadata, False),
            gen.watch_key(app_infos["demo-2"]["prod"].metadata, False),
        }

        dfh.watch.remove_resource(cfg, db, manifests[("demo-2", "prod")])
        cur_keys = set(db.resources["Deployment"].manifests.keys())
        assert cur_keys == {
            gen.watch_key(app_infos["demo-1"]["prod"].metadata, False),
            gen.watch_key(app_infos["demo-2"]["stg"].metadata, False),
        }

        dfh.watch.remove_resource(cfg, db, manifests[("demo-2", "stg")])
        cur_keys = set(db.resources["Deployment"].manifests.keys())
        assert cur_keys == {
            gen.watch_key(app_infos["demo-1"]["prod"].metadata, False),
        }

        dfh.watch.remove_resource(cfg, db, manifests[("demo-1", "prod")])
        cur_keys = set(db.resources["Deployment"].manifests.keys())
        assert cur_keys == set()

    def test_track_resource_lifecycle(self):
        """Add, modify and remove a Deployment."""
        db: Database = Database()
        res = db.resources["Deployment"]
        manifest = yaml.safe_load(Path("tests/support/deployment.yaml").read_text())

        key = "kube-system/coredns"
        for _ in range(3):
            data = {"type": "ADDED", "object": manifest}
            assert not dfh.watch.track_resource(cfg, db, res, data)
            assert len(res.manifests) == 1
            assert key in res.manifests
            assert res.manifests[key] == manifest

        for version in range(3):
            manifest["metadata"]["labels"]["version"] = str(version)
            data = {"type": "MODIFIED", "object": manifest}
            assert not dfh.watch.track_resource(cfg, db, res, data)

            assert len(res.manifests) == 1
            assert key in res.manifests
            assert res.manifests[key] == manifest

        for version in range(3):
            manifest["metadata"]["labels"]["version"] = str(version)
            data = {"type": "DELETED", "object": manifest}
            assert not dfh.watch.track_resource(cfg, db, res, data)

            assert len(res.manifests) == 0

    def test_track_resource_namespace(self):
        """Namespace manifests are slightly special and deserve a dedicated test."""
        db: Database = Database()
        res = db.resources["Namespace"]
        manifest = yaml.safe_load(Path("tests/support/namespace.yaml").read_text())

        key = "/default"
        data = {"type": "ADDED", "object": manifest}
        assert not dfh.watch.track_resource(cfg, db, res, data)
        assert len(res.manifests) == 1
        assert key in res.manifests
        assert res.manifests[key] == manifest

    def test_track_resource_clusterrole(self):
        """Non-namespaced resources are slightly special and deserve a dedicated test."""
        db: Database = Database()
        res = db.resources["ClusterRole"]
        manifest = yaml.safe_load(Path("tests/support/clusterrole.yaml").read_text())

        key = "/cluster-admin"
        data = {"type": "ADDED", "object": manifest}
        assert not dfh.watch.track_resource(cfg, db, res, data)
        assert len(res.manifests) == 1
        assert key in res.manifests
        assert res.manifests[key] == manifest

    def test_track_resource_err(self):
        db: Database = Database()
        res = db.resources["Deployment"]
        manifest = yaml.safe_load(Path("tests/support/deployment.yaml").read_text())

        data = {"type": "invalid", "object": manifest}
        assert dfh.watch.track_resource(cfg, db, res, data)
        assert len(res.manifests) == 0

        data = {"type": "ADDED"}
        assert dfh.watch.track_resource(cfg, db, res, data)
        assert len(res.manifests) == 0
