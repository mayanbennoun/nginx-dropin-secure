# Compatibility Test Suite Design

**Date:** 2026-06-01  
**Topic:** Automated compatibility test suite for the patched nginx image  
**Status:** Approved

---

## Goal

Mathematically prove that `nginx-patched:1.25.5` (the CVE-patched candidate) behaves identically to `nginx:1.25-bookworm` (the upstream baseline) under a representative set of HTTP scenarios. Any observable difference in status code, headers, or body is treated as a regression.

---

## Files Produced

| File | Purpose |
|---|---|
| `test/test_compat.py` | All pytest fixtures, helpers, and test cases |
| `test/requirements.txt` | Adds `docker` SDK to existing `pytest` + `requests` deps |
| `test/nginx-test.conf` | Minimal nginx config that activates all test scenarios |

---

## Architecture — Option A (pytest + Docker SDK fixtures)

### Container Lifecycle

A single **session-scoped** pytest fixture (`nginx_containers`) uses the Docker SDK to:

1. Start `nginx:1.25-bookworm` on host port **8081**
2. Start `$CANDIDATE_IMAGE` (env var, default `nginx-patched:1.25.5`) on host port **8082**
3. Mount `test/nginx-test.conf` into both containers at `/etc/nginx/conf.d/default.conf`
4. `yield` both container handles to tests
5. `stop()` + `remove()` both containers in teardown — runs unconditionally even on test failure

### Request Comparison Helper

A module-level `compare(baseline_url, candidate_url, method, path, **kwargs)` helper:
- Fires the identical request at both endpoints
- Returns `(baseline_resp, candidate_resp)`
- Each test destructs the pair and asserts equality

### Dynamic Header Handling

Before comparing headers, strip all known non-deterministic headers:

```
Date, Age, X-Request-Id, X-Runtime, X-Cache, CF-RAY
```

Only the stripped header dict is compared — no false negatives from timestamp drift.

---

## Test Scenarios

| Test | Method | Path | Payload | What It Verifies |
|---|---|---|---|---|
| `test_get_root` | GET | `/` | — | Default index page, standard request path |
| `test_custom_location` | GET | `/custom` | — | Mounted `nginx-test.conf` is active in both containers |
| `test_post_large_payload` | POST | `/post-test` | 1 MB body | Large-body handling, identical response regardless of payload size |
| `test_malformed_method` | `NOTAMETHOD` | `/` | — | Unknown-method error path (nginx 405/501 behavior) |

---

## nginx-test.conf Layout

```nginx
server {
    listen 80;
    server_name localhost;

    # Scenario 1: standard root request
    location / {
        root /usr/share/nginx/html;
        index index.html;
    }

    # Scenario 2: custom location (proves config mount works)
    location /custom {
        return 200 "custom-ok\n";
        add_header Content-Type "text/plain";
    }

    # Scenario 3: POST target (nginx returns static response regardless of body)
    location /post-test {
        return 200 "post-received\n";
        add_header Content-Type "text/plain";
    }
}
```

---

## Assertions

For every test:

1. **Status code** — must be exactly equal
2. **Headers** — must be equal after stripping dynamic headers listed above
3. **Body** — must be byte-for-byte equal

Failure in any assertion causes the test to fail and pytest to exit non-zero.

---

## Exit Codes

Pytest's native exit codes apply:

| Code | Meaning |
|---|---|
| 0 | All tests passed — images are compatible |
| 1 | One or more tests failed — mismatch detected |
| 2 | Interrupted |
| 3 | Internal error |
| 4 | CLI usage error |
| 5 | No tests collected |

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CANDIDATE_IMAGE` | `nginx-patched:1.25.5` | Docker image tag for the candidate under test |
| `BASELINE_IMAGE` | `nginx:1.25-bookworm` | Docker image tag for the upstream baseline |
| `BASELINE_PORT` | `8081` | Host port mapped to baseline container |
| `CANDIDATE_PORT` | `8082` | Host port mapped to candidate container |

---

## Documentation Comment Block (top of test_compat.py)

The file opens with a Markdown-formatted docstring defining "working correctly":

> **Working correctly** means: for every HTTP scenario in this suite, the candidate image returns a response that is byte-for-byte identical to the baseline in status code, all non-dynamic headers, and body. Dynamic headers (`Date`, etc.) are excluded to prevent false negatives from timestamp drift. A suite run that exits 0 constitutes a compatibility certificate for the candidate image.
