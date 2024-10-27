import asyncio
import json
import logging
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import httpx
import tenacity as tc
from square.k8s import K8sConfig

from dfh.models import K8sPodStatus, PodList

# Convenience: location of K8s credentials inside a Pod.
TOKENFILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
CAFILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")

# Define the exceptions we want to retry on.
WEB_EXCEPTIONS = (httpx.RequestError, ssl.SSLError, KeyError, asyncio.TimeoutError)


# Convenience: global logger instance to avoid repetitive code.
logit = logging.getLogger("square")


def _on_backoff(retry_state: tc.RetryCallState):
    """Log a warning on each retry."""
    attempt = retry_state.attempt_number
    k8sconfig, method, url = retry_state.args[:3]
    path = urlparse(url).path

    logit.warning(f"Back off {attempt} - {k8sconfig.name} - {method} {path}.")


async def _mysleep(delay: float):
    """This trivial function exists to mock out the `sleep` call during tests."""
    await asyncio.sleep(delay)


@tc.retry(
    stop=(tc.stop_after_delay(300) | tc.stop_after_attempt(8)),
    wait=tc.wait_exponential(multiplier=1, min=0, max=20) + tc.wait_random(-5, 5),
    retry=tc.retry_if_exception_type(WEB_EXCEPTIONS),
    before_sleep=_on_backoff,
    reraise=True,
    sleep=_mysleep,
)
async def _call(
    k8sconfig: K8sConfig,
    method: str,
    url: str,
    payload: dict | list | None,
    headers: dict | None,
) -> httpx.Response:
    return await k8sconfig.client.request(method, url, json=payload, headers=headers)


async def request(
    k8sconfig: K8sConfig,
    method: str,
    url: str,
    payload: dict | list | None = None,
    headers: dict | None = None,
) -> Tuple[dict, int, bool]:
    """Return response of web request made with `client`.

    Inputs:
        client: HttpX client with correct K8s certificates.
        url: str
            Eg `https://1.2.3.4/api/v1/namespaces`)
        payload: dict
            Anything that can be JSON encoded, usually a K8s manifest.
        headers: dict
            Request headers. These will *not* replace the existing request
            headers dictionary (eg the access tokens), but augment them.

    Returns:
        (dict, int, bool): the JSON response and the HTTP status code.

    """
    # Make the HTTP request via our backoff/retry handler.
    try:
        ret = await _call(k8sconfig, method, url, payload=payload, headers=headers)
    except WEB_EXCEPTIONS as err:
        logit.error(f"Giving up - {k8sconfig.name} - {err} - {method} {url}")
        return ({}, -1, True)

    # Decode the JSON response and abort if that is impossible.
    try:
        response = json.loads(ret.text)
    except json.decoder.JSONDecodeError as err:
        msg = (
            f"JSON error - {k8sconfig.name} - "
            f"{err.msg} in line {err.lineno} column {err.colno}",
            "-" * 80 + "\n" + err.doc + "\n" + "-" * 80,
        )
        logit.error(str.join("\n", msg))
        return ({}, ret.status_code, True)

    # Log the entire request in debug mode.
    logit.debug(
        f"{method} {ret.status_code} {ret.url}\n"
        f"Headers: {headers}\n"
        f"Payload: {payload}\n"
        f"Response: {response}\n"
    )
    return (response, ret.status_code, False)


async def delete(k8sconfig: K8sConfig, url: str, payload: dict) -> Tuple[dict, bool]:
    """Make DELETE requests to K8s (see `k8s_request`)."""
    resp, code, err = await request(k8sconfig, "DELETE", url, payload, headers=None)
    if err or code not in (200, 202):
        logit.error(f"{code} - DELETE - {url} - {resp}")
        return (resp, True)
    return (resp, False)


async def get(k8sconfig: K8sConfig, url: str) -> Tuple[dict, bool]:
    """Make GET requests to K8s (see `request`)."""
    resp, code, err = await request(k8sconfig, "GET", url, payload=None, headers=None)
    if err or code != 200:
        logit.error(f"{code} - GET - {url} - {resp}")
        return (resp, True)
    return (resp, False)


async def patch(
    k8sconfig: K8sConfig, url: str, payload: List[Dict[str, str]]
) -> Tuple[dict, bool]:
    """Make PATCH requests to K8s (see `request`)."""
    headers = {"Content-Type": "application/json-patch+json"}
    resp, code, err = await request(k8sconfig, "PATCH", url, payload, headers)
    if err or code != 200:
        logit.error(f"{code} - PATCH - {url} - {resp}")
        return (resp, True)
    return (resp, False)


async def post(k8sconfig: K8sConfig, url: str, payload: dict) -> Tuple[dict, bool]:
    """Make POST requests to K8s (see `request`)."""
    resp, code, err = await request(k8sconfig, "POST", url, payload, headers=None)
    err = (code != 201) or err
    if err:
        logit.error(f"{code} - POST - {url} - {resp}")
        return (resp, True)
    return (resp, False)


def parse_pod_info(manifest: dict) -> Tuple[PodList.PodInfo, bool]:
    # Get name and namespace.
    try:
        name, namespace = (
            manifest["metadata"]["name"],
            manifest["metadata"]["namespace"],
        )
        num_containers = len(manifest["spec"]["containers"])
    except KeyError as err:
        logit.error(f"invalid Pod manifest: {err}")
        return PodList.PodInfo(), True

    # Parse the pod status into a Pydantic model.
    pod = K8sPodStatus.model_validate(manifest.get("status", {}))
    num_ready = len([_ for _ in pod.containerStatuses if _.ready])

    # Extract restart count if available.
    if len(pod.containerStatuses) > 0:
        restarts = pod.containerStatuses[0].restartCount
    else:
        restarts = 0

    # Extract age since Pod creation if available.
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(pod.startTime)).seconds
    except ValueError:
        age = 0

    # Extract status message if available. Typically, these message are only
    # available if the pod is unhealthy.
    condition_reason = pod.conditions[-1].reason if len(pod.conditions) > 0 else ""
    condition_message = pod.conditions[-1].message if len(pod.conditions) > 0 else ""

    reasons, messages = [], []
    for status in pod.containerStatuses:
        try:
            r = status.state["waiting"]["reason"]
            m = status.state["waiting"]["message"]
            reasons.append(f"{status.name}: {r}")
            messages.append(f"{status.name}: {m}")
        except KeyError:
            pass
    status_reason = str.join(", ", reasons)
    status_message = str.join(", ", messages)

    # Compile and return the info.
    info = PodList.PodInfo(
        id=f"{namespace}/{name}",
        name=name,
        namespace=namespace,
        phase=pod.phase,
        ready=f"{num_ready}/{num_containers}",
        restarts=restarts,
        age=f"{age:,}s",
        reason=status_reason or condition_reason,
        message=status_message or condition_message,
    )
    return info, False
