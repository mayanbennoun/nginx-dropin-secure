# Compatibility Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write an automated pytest suite that boots both the upstream baseline (`nginx:1.25-bookworm`) and the patched candidate (`nginx-patched:1.25.5`) as ephemeral Docker containers and asserts their HTTP responses are byte-for-byte identical across four scenarios.

**Architecture:** A single session-scoped pytest fixture uses the Docker SDK to start both containers, yield their base URLs to all tests, then stop/remove them on teardown (even on failure). A `compare()` helper fires the same request at both URLs; each test asserts status code, stripped headers, and body match exactly.

**Tech Stack:** Python 3.14, pytest ≥ 8.0, requests ≥ 2.31, docker ≥ 7.0 (SDK), Docker Desktop (via WSL)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `test/requirements.txt` | Add `docker>=7.0` |
| Create | `test/nginx-test.conf` | Minimal nginx config powering all four scenarios |
| Overwrite | `test/test_compat.py` | Doc block, constants, helpers, fixture, four tests |

---

### Task 1: Add Docker SDK to requirements.txt

**Files:**
- Modify: `test/requirements.txt`

- [ ] **Step 1: Edit requirements.txt**

Replace the file contents with:
```
pytest>=8.0
requests>=2.31
docker>=7.0
```

- [ ] **Step 2: Install and verify (run in WSL with venv active)**

```bash
pip install -r test/requirements.txt
python -c "import docker; print(docker.__version__)"
```
Expected: version string like `7.x.x` printed with no errors.

- [ ] **Step 3: Commit**

```bash
git add test/requirements.txt
git commit -m "test: add docker SDK dependency"
```

---

### Task 2: Create test/nginx-test.conf

**Files:**
- Create: `test/nginx-test.conf`

- [ ] **Step 1: Write the config**

Create `test/nginx-test.conf` with this exact content:

```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
    }

    location /custom {
        return 200 "custom-ok\n";
        add_header Content-Type "text/plain";
    }

    location /post-test {
        return 200 "post-received\n";
        add_header Content-Type "text/plain";
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add test/nginx-test.conf
git commit -m "test: add nginx-test.conf for compatibility suite"
```

---

### Task 3: Write test_compat.py — doc block, imports, constants, helpers, fixture

**Files:**
- Overwrite: `test/test_compat.py`

- [ ] **Step 1: Write the failing test skeleton to confirm the fixture is missing**

Overwrite `test/test_compat.py` with just the first test to confirm it fails before the fixture exists:

```python
def test_get_root(nginx_containers):
    baseline_url, candidate_url = nginx_containers
    assert baseline_url.startswith("http://")
```

- [ ] **Step 2: Run to verify it fails with "fixture not found"**

```bash
pytest test/test_compat.py::test_get_root -v
```
Expected: `ERRORS` — `fixture 'nginx_containers' not found`

- [ ] **Step 3: Overwrite test_compat.py with the complete implementation**

Replace the entire file with:

```python
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
        except requests.exceptions.ConnectionError:
            time.sleep(delay)
    raise RuntimeError(
        f"nginx on port {port} did not become ready after {retries * delay:.1f}s"
    )


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
```

- [ ] **Step 4: Verify pytest can collect all four tests**

```bash
pytest test/test_compat.py --collect-only
```

Expected output (4 items collected, no errors):
```
<Module test_compat.py>
  <Function test_get_root>
  <Function test_custom_location>
  <Function test_post_large_payload>
  <Function test_malformed_method>
```

- [ ] **Step 5: Commit**

```bash
git add test/test_compat.py
git commit -m "test: implement nginx compatibility test suite"
```

---

### Task 4: Run the full suite end-to-end

**Files:** none — integration run only

- [ ] **Step 1: Pull the baseline image (if not already present)**

```bash
docker pull nginx:1.25-bookworm
```

- [ ] **Step 2: Ensure the candidate image is built**

```bash
docker images nginx-patched:1.25.5
```

If the image is not listed, build it from the repo root:
```bash
make image
```

- [ ] **Step 3: Run the full suite**

```bash
pytest test/test_compat.py -v
```

Expected output:
```
test/test_compat.py::test_get_root            PASSED
test/test_compat.py::test_custom_location     PASSED
test/test_compat.py::test_post_large_payload  PASSED
test/test_compat.py::test_malformed_method    PASSED

4 passed in X.XXs
```

Exit code must be `0`. If any test fails, the assertion message will identify which field (status/headers/body) diverged between baseline and candidate.

- [ ] **Step 4: Verify containers were cleaned up**

```bash
docker ps -a | grep -E "nginx:1.25-bookworm|nginx-patched"
```

Expected: no output (both containers removed by fixture teardown).
