# nginx-patched-build

Drop-in replacement for container with targeted CVE remediation. The patched image is built from the upstream nginx 1.25.5 source tarball (with backported fixes), packaged as a signed `.deb`, and assembled on `debian:bookworm-slim`.

---

## Directory layout

```
nginx-patched-build/
├── build/
│   ├── Dockerfile.build        # Multi-stage build: patches source → .deb
│   ├── build.sh                # Orchestrates patching + Docker build + .deb extraction
│   ├── dist/                   # Output: compiled .deb packages (git-ignored)
│   │   ├── nginx_1.25.5-1~bookworm_amd64.deb
│   │   └── nginx-dbg_1.25.5-1~bookworm_amd64.deb
│   ├── patches/
│   │   └── CVE-2026-9256.patch # Backport from nginx mainline commit ca4f92a
│   └── sources/
│       ├── nginx-1.25.5-upstream.tar.gz   # Original upstream tarball (unmodified)
│       └── nginx-1.25.5.tar.gz            # Patched tarball (fed into Dockerfile.build)
├── docker-entrypoint/
│   ├── docker-entrypoint.sh
│   ├── 10-listen-on-ipv6-by-default.sh
│   ├── 15-local-resolvers.envsh
│   ├── 20-envsubst-on-templates.sh
│   └── 30-tune-worker-processes.sh
├── reports/
│   ├── baseline/
│   │   ├── baseline-grype.txt      # Grype scan of nginx:1.25-bookworm
│   │   ├── baseline-trivy.txt      # Trivy scan of nginx:1.25-bookworm
│   └── patched/
│       ├── patched-grype.txt       # Grype scan of nginx-patched:1.25.5
│       └── patched-trivy.txt       # Trivy scan of nginx-patched:1.25.5
├── test/
│   ├── test_compat.py          # Pytest suite: byte-identical response comparison
│   ├── nginx-test.conf         # Shared nginx config mounted in both containers
│   └── requirements.txt
├── Containerfile               # Runtime image: debian:bookworm-slim + patched .deb
├── Makefile                    # Convenience targets: build-deb / image / test
├── README.md
└── vex.json                    # OpenVEX statements for scanner-visible residuals
```

---

## Build instructions

### Prerequisites

- Docker (with BuildKit)
- `bash`, `curl`, `patch` (standard on Linux/macOS; on Windows use WSL or Git Bash)
- Python 3.9+ with `venv` (for running compatibility tests)

### Quick start (via Makefile)

```bash
# Build the .deb, assemble the image, and run all compatibility tests:
make all

# Individual targets:
make build-deb   # Apply patches, compile nginx, extract .deb to build/dist/
make image       # Build runtime image nginx-patched:1.25.5 from Containerfile
make test        # Spin up baseline + candidate containers and diff HTTP responses
```

### Step-by-step (manual)

**1. Apply CVE patches and compile the .deb**

```bash
bash build/build.sh
# Produces: build/dist/nginx_1.25.5-1~bookworm_amd64.deb
```

The script:
- Downloads the nginx 1.25.5 upstream tarball if not already present
- Applies every `.patch` file found in `build/patches/`
- Re-tarballs the patched source and passes it to `Dockerfile.build`
- Runs a Docker build that clones `nginx/pkg-oss`, injects a hardened `libssl3 (>= 3.0.14)` dependency floor, and compiles the `.deb`
- Extracts the `.deb` from the build container into `build/dist/`

**2. Build the runtime image**

```bash
docker build -f Containerfile -t nginx-patched:1.25.5 .
```

**3. Scan the patched image**

```bash
grype nginx-patched:1.25.5 --only-fixed
trivy image nginx-patched:1.25.5
```

Compare results against `reports/baseline/` to verify CVE reduction.

**4. Run compatibility tests**

```bash
python3 -m venv test/.venv
test/.venv/bin/pip install -r test/requirements.txt
test/.venv/bin/pytest test/ -v -s
```

The test suite starts both `nginx:1.25-bookworm` (baseline) and `nginx-patched:1.25.5` (candidate) via the Docker SDK and asserts byte-identical HTTP responses for four scenarios: GET /, GET /custom, POST 1 MB body, and a malformed method.

---

## Image size: original vs. patched

| Image | Uncompressed size | Notes |
|---|---|---|
| `nginx:1.25-bookworm` (baseline) | 187 MB | Official image, Debian Bookworm |
| `nginx-patched:1.25.5` | 188 MB | `debian:bookworm-slim` + patched nginx .deb + gettext-base + curl |

The patched image is ~1 MB larger than the baseline — a negligible overhead for a security-hardened build. Sizes measured via `docker inspect --format '{{.Size}}'`.

---

## Per-CVE remediation table

| CVE | Severity | EPSS | Package | Fix method | What was done | Evidence |
|---|---|---|---|---|---|---|
| **CVE-2026-9256** | Critical | 0.2% | nginx 1.25.5 | Backport | Cherry-picked nginx mainline commit `ca4f92a` (Roman Arutyunyan) which fixes `ngx_http_script_regex_start_code()` to iterate per-capture when computing escape overhead, eliminating the under-allocation that caused the heap overflow. Patch applied to source before `.deb` compilation. | `build/patches/CVE-2026-9256.patch`, `vex.json` |
| **CVE-2024-6119** | High | 14.6% | libssl3 / openssl | Version bump | Injected an explicit `libssl3 (>= 3.0.14)` floor into the nginx `.deb` control file during `Dockerfile.build`. This forces `dpkg` to refuse installation unless a fixed OpenSSL is present. At runtime `apt-get` installs `libssl3 3.0.20-1~deb12u1`, which exceeds the fix threshold. | `build/Dockerfile.build` line 45, `reports/patched/patched-grype.txt` (openssl version `3.0.20`) |
| **CVE-2025-27363** | High (KEV) | 70.8% | libfreetype6 | Version bump | libfreetype6 is resolved at `2.12.1+dfsg-5+deb12u4` in the patched image (above the `+deb12u4` fix threshold). The package is absent from the patched scanner output, confirming remediation. This was the highest-risk CVE in the baseline scan (risk score 81.9, actively exploited). | `reports/patched/patched-grype.txt` (libfreetype6 not present), `reports/baseline/baseline-grype.txt` line 2 |

> **Disclaimer (CVE-2023-44487):** This is a scanner false positive — the HTTP/2 Rapid Reset fix shipped in nginx 1.25.3, so the 1.25.5 binary we compile is not affected. The alert persists only because the Debian package metadata never received a DSA.

---

## Residual risk assessment

The patched image still has scanner-visible CVEs. Here is what remains, why, and what the next step would be.

### Still flagged — scanner artefact (binary is safe)

| CVE | Package | Why it persists | Action |
|---|---|---|---|
| CVE-2026-9256 | nginx | Package version string `1.25.5-1~bookworm` is unchanged after applying the patch; scanner matches on version metadata, not binary content. | Add a VEX `not_affected` / `inline_mitigation_already_exist` statement (partially done) or bump the epoch in the `.deb` version. |
| CVE-2023-44487 | nginx | Same reason — Debian never issued a DSA, so scanner keyed on package version. The fix is in the compiled binary. | Add VEX statement. |

### Still flagged — genuine residuals, no upstream fix available

| CVE | Package | Severity | Why it remains |
|---|---|---|---|
| CVE-2013-0337 | nginx | Low | Debian `won't fix`; very old, no exploitable path in a containerised nginx. |
| CVE-2026-42946 | nginx | Medium | Debian `won't fix` in Bookworm. |
| CVE-2023-6277, CVE-2023-52355 | libtiff6 | Medium/High | Debian `won't fix`; libtiff is a transitive dependency of nginx's image-filter module. |
| CVE-2023-2953 | libldap-2.5-0 | High | Debian `won't fix`; LDAP is not used in a standard nginx deployment. |
| CVE-2024-56433 | login/passwd | Low | Debian `won't fix`; affects PAM login stack, irrelevant in a container running as non-root nginx. |

### Still flagged — real risk, fixable with more time

These are the only scanner-visible residuals that have a fix available (i.e. not Debian `won't fix`). Both are resolved by a single dependency bump in the Containerfile `apt-get` layer.

| CVE(s) | Package | Severity | Installed → Fixed in | Suggested next action |
|---|---|---|---|---|
| CVE-2026-33845, CVE-2026-42010 (Critical); CVE-2026-42009 / 42011 / 42012 / 42013 / 5260 / 3833 / 33846 (High) | libgnutls30 | Critical | `3.7.9-2+deb12u6` → `3.7.9-2+deb12u7` | Pin `libgnutls30=3.7.9-2+deb12u7` in the Containerfile; clears 2 Critical + 7 High in one upgrade. |
| CVE-2026-41989 | libgcrypt20 | Medium | `1.10.1-3` → `1.10.1-3+deb12u1` | Pin `libgcrypt20=1.10.1-3+deb12u1` in the Containerfile. |

**Overall posture:** The two highest-priority KEV items (CVE-2025-27363) and the critical nginx-specific vulnerability (CVE-2026-9256) are remediated. The remaining high/critical items are in libraries that nginx loads transitively but does not exercise in a default configuration. None of the remaining "won't fix" items have a CVSS exploit chain that passes through the nginx HTTP request path.

---

## What surprised me, and what I'd do differently

### Surprises

**1. CVE-2023-44487 is a false positive.** The HTTP/2 Rapid Reset fix shipped in nginx 1.25.3 — eight months before 1.25.5. The Debian packaging team never issued a DSA because the upstream package already contained the fix. Every scanner that keys on Debian package metadata will flag it indefinitely. This is the strongest argument for building from source: the compiled binary is clean even though the package metadata is not.

**2. The scanner cannot distinguish patched binaries from unpatched ones.** After backporting CVE-2026-9256, Grype still flags the nginx package because version `1.25.5-1~bookworm` matches its vulnerability database. VEX exists precisely for this — it is the standard way to assert "yes the scanner sees this, but here is why the binary is safe."

**3. A single OpenSSL bump cleared far more CVEs than anticipated.** My initial plan was only to resolve CVE-2024-6119, but forcing the hardened `libssl3` floor cleared 27 `libssl3`/openssl CVEs in one move (2 Critical, 12 High, 13 Medium):

| Severity | CVEs |
|---|---|
| Critical | CVE-2024-5535, CVE-2026-31789 |
| High | CVE-2024-4741, CVE-2024-6119, CVE-2025-15467, CVE-2025-69419, CVE-2025-69420, CVE-2025-69421, CVE-2025-9230, CVE-2026-28387, CVE-2026-28388, CVE-2026-28389, CVE-2026-28390, CVE-2026-31790 |
| Medium | CVE-2023-5678, CVE-2023-6129, CVE-2023-6237, CVE-2024-0727, CVE-2024-13176, CVE-2024-2511, CVE-2024-4603, CVE-2024-9143, CVE-2025-68160, CVE-2025-69418, CVE-2025-9232, CVE-2026-22795, CVE-2026-22796 |

### What I'd do differently with more time
- **Pin explicit package versions** for all libssl3, libexpat1, and libkrb5 in the Containerfile RUN layer, rather than relying on whatever `apt-get` resolves to at build time. This makes the image reproducible and the fix traceable.
- I would generate a flow to automate this process: detect available version bumps and released patches, and automate the container patching pipeline.

---

## AI Tool Utilization

Claude Code was used throughout this project as a pair-programmer and security analyst:

| Task | AI contribution |
|---|---|
| **CVE triage** | Analysed the 472-row Grype baseline scan, ranked CVEs by EPSS × KEV status × fix availability, and produced `reports/baseline/triage-hypothesis.md` with the selection rationale for each remediation slot. |
| **Dockerfile.build** | Drafted the multi-stage build that clones `nginx/pkg-oss`, injects the OpenSSL dependency floor via `sed`, and resolves the `hg.nginx.org` mirror failure by locating the `freenginx.org` alternative and generating the SHA-512 integrity check. |
| **build.sh** | Wrote the patching loop (`for patch in patches/*.patch`) that applies all `.patch` files before re-tarballing the source. |
| **Containerfile** | Adapted the official nginx Dockerfile to install from the locally-built `.deb` instead of the upstream repo, and added the `dpkg -i --force-overwrite` step to replace the official binary with the patched one after dependency resolution. |
| **vex.json** | Generated the OpenVEX document for CVE-2026-9256 with the correct `inline_mitigation_already_exist` justification and the commit-level action statement. |

Gemini was used as a tool for brainstorming, understanding task scope and specifics, and also as an explanatory tool to clarify the CVEs and their remediation.

I felt AI assisted in reviewing CVE data, surfacing candidate CVEs to focus on and verify, and debugging Docker image build bugs — but when generating the Docker image build it tended to over-simplify and strip out core features. 