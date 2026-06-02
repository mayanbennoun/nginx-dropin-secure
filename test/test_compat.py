"""
# nginx Compatibility Test Suite

## What "working correctly" means

A candidate nginx image is considered **working correctly** when, for every HTTP
scenario in this suite, it returns a response that is **byte-for-byte identical**
to the upstream baseline (`nginx:1.25-bookworm`) in:

- **Status code** — exact integer match
- **Headers** — exact match after stripping non-deterministic headers (`Date`,
  `Age`, `X-Request-Id`, `X-Runtime`, `X-Cache`, `CF-RAY`)
- **Body** — exact byte match

A suite run that exits 0 is a **compatibility certificate** for the candidate image.

## Test Coverage

| Test                    | Method      | Path        | Payload | Verifies                                     |
|-------------------------|-------------|-------------|---------|----------------------------------------------|
| test_get_root           | GET         | /           | —       | Standard request / default index page        |
| test_custom_location    | GET         | /custom     | —       | Mounted nginx-test.conf is active in both    |
| test_post_large_payload | POST        | /post-test  | 1 MB    | Large-body handling is identical             |
| test_malformed_method   | NOTAMETHOD  | /           | —       | Unknown-method error path                    |

## Configuration (environment variables)

| Variable        | Default               | Purpose                        |
|-----------------|-----------------------|--------------------------------|
| CANDIDATE_IMAGE | nginx-patched:1.25.5  | Image under test               |
| BASELINE_IMAGE  | nginx:1.25-bookworm   | Upstream reference             |
| BASELINE_PORT   | 8081                  | Host port for baseline container |
| CANDIDATE_PORT  | 8082                  | Host port for candidate container |
"""

import os
import time
from pathlib import Path

import docker
import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASELINE_IMAGE = os.environ.get("BASELINE_IMAGE", "nginx:1.25-bookworm")
CANDIDATE_IMAGE = os.environ.get("CANDIDATE_IMAGE", "nginx-patched:1.25.5")
BASELINE_PORT = int(os.environ.get("BASELINE_PORT", "8081"))
CANDIDATE_PORT = int(os.environ.get("CANDIDATE_PORT", "8082"))

NGINX_CONF_PATH = str(Path(__file__).parent / "nginx-test.conf")

DYNAMIC_HEADERS = {"date", "age", "x-request-id", "x-runtime", "x-cache", "cf-ray"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_nginx(port: int, retries: int = 20, delay: float = 0.5) -> None:
    """Poll until nginx accepts connections or raise RuntimeError."""
    url = f"http://localhost:{port}/"
    for _ in range(retries):
        try:
            requests.get(url, timeout=1)
            return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            time.sleep(delay)
    raise RuntimeError(
        f"nginx on port {port} did not become ready after {retries * delay:.1f}s"
    )


def _cleanup_existing(client, ports):
    """Remove any leftover containers occupying the given host ports."""
    for container in client.containers.list(all=True):
        for binding in container.ports.values():
            if binding and any(int(b["HostPort"]) in ports for b in binding):
                try:
                    container.stop(timeout=2)
                except Exception:
                    pass
                try:
                    container.remove()
                except Exception:
                    pass
                break


def strip_dynamic(headers: dict) -> dict:
    """Return headers with all known non-deterministic keys removed."""
    return {k: v for k, v in headers.items() if k.lower() not in DYNAMIC_HEADERS}


def compare(baseline_url: str, candidate_url: str, method: str = "GET", path: str = "/", **kwargs):
    """Fire the same request at both endpoints and return (baseline_resp, candidate_resp)."""
    b = requests.request(method, baseline_url + path, **kwargs)
    c = requests.request(method, candidate_url + path, **kwargs)
    return b, c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nginx_containers():
    """Boot baseline and candidate containers; yield their base URLs; tear down on exit."""
    client = docker.from_env()
    _cleanup_existing(client, {BASELINE_PORT, CANDIDATE_PORT})
    volumes = {NGINX_CONF_PATH: {"bind": "/etc/nginx/conf.d/default.conf", "mode": "ro"}}

    baseline = client.containers.run(
        BASELINE_IMAGE,
        detach=True,
        ports={"80/tcp": BASELINE_PORT},
        volumes=volumes,
    )
    candidate = client.containers.run(
        CANDIDATE_IMAGE,
        detach=True,
        ports={"80/tcp": CANDIDATE_PORT},
        volumes=volumes,
    )

    _wait_for_nginx(BASELINE_PORT)
    _wait_for_nginx(CANDIDATE_PORT)

    yield (
        f"http://localhost:{BASELINE_PORT}",
        f"http://localhost:{CANDIDATE_PORT}",
    )

    for container in (baseline, candidate):
        try:
            container.stop(timeout=5)
        except Exception:
            pass
        try:
            container.remove()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_root(nginx_containers):
    baseline_url, candidate_url = nginx_containers
    b, c = compare(baseline_url, candidate_url, method="GET", path="/")
    assert b.status_code == c.status_code, f"status mismatch: {b.status_code} != {c.status_code}"
    assert strip_dynamic(dict(b.headers)) == strip_dynamic(dict(c.headers)), "headers mismatch"
    assert b.content == c.content, "body mismatch"


def test_custom_location(nginx_containers):
    baseline_url, candidate_url = nginx_containers
    b, c = compare(baseline_url, candidate_url, method="GET", path="/custom")
    assert b.status_code == c.status_code, f"status mismatch: {b.status_code} != {c.status_code}"
    assert strip_dynamic(dict(b.headers)) == strip_dynamic(dict(c.headers)), "headers mismatch"
    assert b.content == c.content, "body mismatch"


def test_post_large_payload(nginx_containers):
    baseline_url, candidate_url = nginx_containers
    payload = b"x" * (1024 * 1024)  # 1 MB
    b, c = compare(baseline_url, candidate_url, method="POST", path="/post-test", data=payload)
    assert b.status_code == c.status_code, f"status mismatch: {b.status_code} != {c.status_code}"
    assert strip_dynamic(dict(b.headers)) == strip_dynamic(dict(c.headers)), "headers mismatch"
    assert b.content == c.content, "body mismatch"


def test_malformed_method(nginx_containers):
    baseline_url, candidate_url = nginx_containers
    b, c = compare(baseline_url, candidate_url, method="NOTAMETHOD", path="/")
    assert b.status_code == c.status_code, f"status mismatch: {b.status_code} != {c.status_code}"
    assert strip_dynamic(dict(b.headers)) == strip_dynamic(dict(c.headers)), "headers mismatch"
    assert b.content == c.content, "body mismatch"
