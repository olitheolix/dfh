"""Watch a K8s resource.

This is a produce consumer problem. The produce will tail K8s and put the
events into a local queue. The consumer is the actual iterator, ie the
__anext__ method that pulls the queue until it receives a DONE message.

The background task will keep itself indefinitely. The only exception is an
`asyncio.CancelledError` that will force it to shut down.

The background task will first fetch all resources to determine the most
recent ID. Then it will open a long lived connection to the watch endpoint
starting from the most recent ID and forward the event stream into a local
queue. This continues until the connection dies or K8s responds with 410
(Gone). At that point, the task closes the connection, records the most recent
ID and starts over.
"""

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple

import square.k8s
from square.dtypes import ConnectionParameters, K8sConfig

import dfh.generate
import dfh.k8s
from dfh.manifest_utilities import get_metainfo
from dfh.models import AppMetadata, Database, ServerConfig, WatchedResource

# Convenience.
logit = logging.getLogger("app")


class WatchResource:
    """Track resource changes over time.

    Usage:

    kubeconfig = Path("/tmp/kind-kubeconf.yaml")
    kubecontext = "kind-kind"
    k8scfg, err = dfh.watch.create_cluster_config(kubeconfig, kubecontext)
    assert not err
    watch = dfh.watch.WatchResource(k8scfg, "/api/v1/namespaces")
    async for data in watch:
        evt, manifest = data["type"], data["object"]
        print(evt, manifest["metadata"]["name"])

    """

    def __init__(
        self,
        k8scfg: K8sConfig,
        path: str,
        rv: int = -1,
        timeout: int = 5,
        logger: logging.Logger = logging.getLogger("Watch"),
    ):
        self.logit = logger
        self.k8scfg = k8scfg

        self.last_rv: int = rv  # Last seen resource version.
        self.list_path: str = path  # Resource path, eg "/api/crt/v1/namespaces"
        self.timeout = timeout  # Request this timeout from K8s.
        self.queue: asyncio.Queue = asyncio.Queue()

        # Track our current knowledge as a `{UID: manifest}` dict.
        self.state: Dict[str, dict] = {}

        self.watch_path = f"{path}?watch=true&timeoutSeconds={self.timeout}"

        # Start the background tasks.
        self.tasks = self.start_tasks()

    def start_tasks(self):
        return [asyncio.create_task(self.background_runner())]

    def stop_tasks(self):
        for task in self.tasks:
            task.cancel()

    def __aiter__(self):  # codecov-skip
        return self

    async def __anext__(self):
        while True:
            # Wait for the next event.
            event = await self.queue.get()

            # If the background task was cancelled or raised an unhandled
            # exception we will stop the iterator.
            if event in ("__EXCEPTION__", "__CANCELLED__"):
                self.tasks[0].result()  # NOTE: raises exception if there was one.
                raise StopAsyncIteration
            return event

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.stop_tasks()

    def get_logging_metadata(self) -> dict:
        url = self.k8scfg.client._base_url
        host = str(url) if url else ""
        meta_log = {
            "component": "k8s-watch",
            "path": self.list_path,
            "host": host,
        }
        return meta_log

    def construct_watch_path(self, rv: int) -> str:
        return f"{self.watch_path}&resourceVersion={rv}"

    async def list_resource(self) -> Tuple[int, bool]:
        """Download the latest manifests of the resource and return the last RV.

        This function will also sync the internal state and create fake events
        to update the old state to the new one.

        """
        # Fetch the current set of manifests.
        ret, err = await dfh.k8s.get(self.k8scfg, self.list_path)
        if err:
            return (-1, True)

        # Sync the current state with the new manifests.
        await self.reset_state(ret["items"], self.state)

        # Return the resource version as an integer.
        last_resver = int(ret["metadata"]["resourceVersion"])
        return last_resver, False

    async def reset_state(
        self, manifests: List[dict], old_state: Dict[str, dict]
    ) -> None:
        """Reset the state to the new `manifests`.

        The function will emit the corresponding ADDED, MODIFIED, DELETED
        events to transition the `old_state` into one that represents the
        current set of `manifests`.

        This function should only be called from `list_resource`.

        It is important to note that the `old_state` will represent the current
        state and is independent of the iterator that yields the change events.
        As such, the internal state of this class may be ahead of that one seen
        by the consumer of the iterator.

        This function is typically called from `list_resources` to sync the
        internal state after a reconnect to K8s.

        NOTE: this function will modify the `old_state` in-place.

        """
        new_state = {_["metadata"]["uid"]: _ for _ in manifests}
        new_keys = set(new_state)
        old_keys = set(old_state)

        # Remove the UIDs that no longer exist in the new state.
        to_remove = old_keys - new_keys
        for uid in to_remove:
            obj = old_state.pop(uid)
            await self.queue.put({"type": "DELETED", "object": obj})

        # Add the UIDs that are new.
        to_add = new_keys - old_keys
        for uid in to_add:
            obj = new_state[uid]
            old_state[uid] = obj
            await self.queue.put({"type": "ADDED", "object": obj})

        # Sanity check
        assert set(new_state) == set(old_state)

        # Emit a MODIFIED event for all objects that have changed.
        for uid, new_obj in new_state.items():
            if old_state[uid] != new_obj:
                old_state[uid] = new_obj
                await self.queue.put({"type": "MODIFIED", "object": new_obj})

    async def update_state(self, k8s_line_json):
        """Forward K8s `k8s_line_json` to the iterator queue and track state.

        This function is usually called from `parse_line` in order to process
        an update event from K8s. Specifically, it will add the event to the
        iterator queue and update the internal state.

        """
        meta_log = self.get_logging_metadata()

        event, obj = k8s_line_json["type"], k8s_line_json["object"]

        # Track the latest resource version and enqueue the event.
        self.last_rv = int(obj["metadata"]["resourceVersion"])

        # Sanity check.
        assert event in ("ADDED", "MODIFIED", "DELETED")

        # Update the state.
        uid = obj["metadata"]["uid"]
        if event.upper() == "ADDED":
            # If the UID is already in the state convert ADDED to MODIFIED.
            if uid in self.state:
                self.logit.error(f"Bug: Add existing UID <{uid}>", meta_log)
                k8s_line_json["type"] = "MODIFIED"

            # Update the state and queue the event.
            self.state[uid] = obj
            await self.queue.put(k8s_line_json)

        elif event.upper() == "MODIFIED":
            # If the UID is not in our state convert MODIFIED to ADDED.
            if uid not in self.state:
                self.logit.error(f"Bug: Modify non-existing UID <{uid}>", meta_log)
                k8s_line_json["type"] = "ADDED"

            # Update the state and queue the event.
            await self.queue.put(k8s_line_json)
            self.state[uid] = obj

        else:
            # Do nothing if we do not have that UID.
            if uid not in self.state:
                self.logit.error(f"Bug: Remove non-existing UID <{uid}>", meta_log)
            else:
                del self.state[uid]
                await self.queue.put(k8s_line_json)

    async def parse_line(self, line_raw: str) -> bool:
        """Forward K8s events to the iterator queue for as long as possible.

        The function accepts an already open connection `resp` to K8s and then
        reads the responses line by line until K8s closes the connection or an
        error occurs.

        """
        meta_log = self.get_logging_metadata()

        # Return without error if K8s terminates the watch. This is
        # expected from time to time and simply means we need to restart
        # the watch from the last known resource version.
        if len(line_raw) == 0:
            self.logit.info("Connection closed", meta_log)
            return False

        # K8s sends JSON encoded lines.
        try:
            line_json = json.loads(line_raw)
        except json.JSONDecodeError:
            self.logit.error("K8s sent corrupt JSON payload", meta_log)
            return True

        # Abort if we received an ERROR or unexpected event.
        event, manifest = line_json["type"], line_json["object"]
        if event.upper() not in ("ADDED", "DELETED", "MODIFIED"):
            meta_log["msg"] = manifest
            self.logit.info("Received error from K8s", meta_log)

            # A 410 (Gone) error is harmless and expected. We therefore
            # return without error to signal to the caller that we can (and
            # probably should) resume the watch immediately.
            if event.upper() == "ERROR" and manifest["code"] == 410:
                return False

            # Let the caller know that something unexpectedly happened. The
            # logs will contain the details.
            return True

        # Add event to queue and track the state.
        await self.update_state(line_json)
        return False

    async def read_k8s_stream(self) -> bool:
        """Connect to K8s and consume events for as long as possible.

        Return `True` if the connection dropped due to a genuine problem like a
        network error or an unhandled exception. This does not include 410
        responses or K8s closing the connection cleanly since this is expected
        to happen from time to time and simply means we should reconnect.

        """
        # Fetch the current resource list if the resource version `rv` is negative.
        if self.last_rv < 0:
            rv, err = await self.list_resource()
            if err:
                return True
            self.last_rv = rv

        # Construct the URL for a long lived watch connection.
        url = self.construct_watch_path(self.last_rv)

        # Open the long lived connection.
        try:
            async with self.k8scfg.client.stream("GET", url) as stream:
                if stream.status_code != 200:
                    meta_log = self.get_logging_metadata()
                    self.logit.warning("Cannot start watch", meta_log)
                    return True

                # Feed the K8s events into our local iterator queue.
                async for line_raw in stream.aiter_lines():
                    await self.parse_line(line_raw)
        except dfh.k8s.WEB_EXCEPTIONS:
            meta_log = self.get_logging_metadata()
            self.logit.exception("Watch aborted due to an web exception", meta_log)
            return True
        return False

    async def background_runner(self) -> None:
        """Watch the K8s resource indefinitely.

        This method perpetually restarts `read_k8s_stream` and does
        not return unless it receives a `CancelledError` or encounters an
        unhandled exception (ie bug).

        """
        meta_log = self.get_logging_metadata()
        try:
            # Perpetually restart the background runner.
            while True:
                self.logit.info("Reconnect", meta_log)
                if await self.read_k8s_stream():
                    # Wait a bit before we try to resume the watch.
                    await asyncio.sleep(5 + random.uniform(-2, 2))
        except asyncio.CancelledError:
            self.logit.info("Background task was cancelled", meta_log)
            await self.queue.put("__CANCELLED__")
        except Exception as err:
            self.logit.exception("Unhandled exception", meta_log)
            await self.queue.put("__EXCEPTION__")
            raise err


def create_cluster_config(kubeconf: Path, context: str) -> Tuple[K8sConfig, bool]:
    # Parse Kubeconfig file.
    cfg, err = square.k8s.load_auto_config(kubeconf, context)
    if err:
        return K8sConfig(), True

    # Create HTTPX client.
    params = ConnectionParameters(read=600, write=600, pool=600)
    cfg, err = square.k8s.create_httpx_client(cfg, params)
    if err:
        return K8sConfig(), True

    # Set the base URL to the K8s API server for convenience.
    cfg.client.base_url = cfg.url

    return cfg, False


async def setup_k8s_watch(
    cfg: ServerConfig, k8scfg: K8sConfig, db: Database, res: WatchedResource
):
    # Setup log stream with INFO severity.
    logit.info(f"watch started for {res.apiVersion}/{res.kind}")

    # Watch the specified resource `res` and re-establish the watch every ~2min.
    try:
        timeout = 120 + int(random.uniform(-10, 10))
        watch = WatchResource(k8scfg, res.path, timeout=timeout, logger=logit)
        async with k8scfg.client, watch:
            async for data in watch:  # codecov-skip
                track_resource(cfg, db, res, data)
    except asyncio.CancelledError:
        logit.info("watch cancelled")


def get_resource_key(manifest: dict) -> Tuple[str, str, bool]:
    # Extract meta data and abort on error.
    try:
        name = manifest["metadata"]["name"]
        kind = manifest["kind"]
    except KeyError:
        return "", "", True

    # The namespace is optional, eg `ClusterRole`.
    namespace = manifest["metadata"].get("namespace", "")

    # Use `watch_key` helper to produce the final resource key.
    # NOTE: it is always `canary=False` because the watch bases its key name on
    # the actual K8s resource names which may or may not already include the
    # `-canary` prefix.
    meta = AppMetadata(name=name, env="", namespace=namespace)
    key = dfh.generate.watch_key(meta, canary=False)

    # Database key, eg `default/coredns`.
    return key, kind, False


def upsert_resource(cfg: ServerConfig, db: Database, manifest: dict):
    key, kind, err = get_resource_key(manifest)
    if err:
        return

    # Track the resource in our general DB.
    db.resources[kind].manifests[key] = manifest

    meta, err = get_metainfo(cfg, manifest)
    if err:
        return

    # Return immediately if the manifest does not belong to one of our apps.
    try:
        db.apps[meta.name][meta.env].resources[kind].manifests[key] = manifest
    except KeyError:
        pass


def remove_resource(cfg: ServerConfig, db: Database, manifest: dict):
    key, kind, err1 = get_resource_key(manifest)

    # Track the resource in our general DB.
    db.resources[kind].manifests.pop(key, None)

    meta, err2 = get_metainfo(cfg, manifest)
    if err1 or err2:
        return

    try:
        db.apps[meta.name][meta.env].resources[kind].manifests.pop(key, None)
    except KeyError:
        pass


def track_resource(
    cfg: ServerConfig, db: Database, res: WatchedResource, data: dict
) -> bool:
    # Extract meta data and abort on error.
    try:
        evt, manifest = data["type"], data["object"]
    except KeyError:
        return True

    # Update our internal database.
    if evt in {"ADDED", "MODIFIED"}:
        manifest["kind"] = res.kind
        manifest["apiVersion"] = res.apiVersion

        upsert_resource(cfg, db, manifest)
    elif evt == "DELETED":
        remove_resource(cfg, db, manifest)
    else:
        return True
    return False
