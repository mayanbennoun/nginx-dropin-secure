# CVE Triage Hypothesis — nginx:1.25-bookworm

## Image under test

| Field         | Value |
|---------------|-------|
| Tag           | `nginx:1.25-bookworm` |
| Digest        | `sha256:a484819eb60211f5299034ac80f6a681b06f89e65866ce91f356ed7c72af059c` |
| NGINX_VERSION | **1.25.5** (PKG_RELEASE `1~bookworm`) |
| NJS_VERSION   | `0.8.4` |
| Base OS       | Debian Bookworm, amd64 |
| Build date    | 2024-05-03 |

Scanned with Trivy + Grype before any patching.

---

## Scanner summary

| Scanner | Findings | Notable |
|---------|----------|---------|
| Grype   | 472 rows | 2 KEV-listed, 8 Critical, 15+ High |
| Trivy   | Full JSON (`baseline-trivy.txt`) | Corroborates Grype |

**KEV-listed (actively exploited in the wild):**
- **CVE-2025-27363** — libfreetype6 (Risk 81.9, EPSS 70.8%)
- **CVE-2023-44487** — nginx Debian package (Risk 78.8, EPSS 94.4%) — *see note below, not a real exposure*

---

## Note: CVE-2023-44487 is a false positive in our build

CVE-2023-44487 (HTTP/2 Rapid Reset) was fixed upstream in nginx **1.25.3** (Oct 2023). We ship **1.25.5**, so the fix is already in the source tarball we compile from.

The scanner flags it only because the Debian package `1.25.5-1~bookworm` never got a DSA — Debian didn't issue one since the nginx.org mainline packages already contained the fix. Building from the upstream tarball produces a clean binary regardless of the package metadata.

**Disposition:** document in `vex.json` as `status: not_affected`, `justification: vulnerable_code_not_present`. Not a valid backport target. It's a good illustration of why building from source beats the Debian repackaged binary.

---

## Case 1 — Fix by dependency version bump

Update a system library or upstream source to a version containing the fix; no manual source patching.

### 1A — libfreetype6 / CVE-2025-27363 *(top candidate)*

| Field    | Value |
|----------|-------|
| Installed / Fixed | `2.12.1+dfsg-5` → `2.12.1+dfsg-5+deb12u4` |
| Severity | High · EPSS 70.8% (98th pct) · **Risk 81.9 — highest in scan** |
| KEV      | Yes |
| Type     | Out-of-bounds write in FreeType |

The only CVE in the scan with risk above 10, by a wide margin. KEV-listed, single-package fix, clean before/after diff.

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6=2.12.1+dfsg-5+deb12u4 \
    && rm -rf /var/lib/apt/lists/*
```

### 1B — OpenSSL / CVE-2024-5535 + CVE-2024-6119 *(strong alternative)*

| CVE | Installed | Fixed in | Severity | EPSS |
|-----|-----------|----------|----------|------|
| CVE-2024-5535 | 3.0.11-1~deb12u2 | 3.0.15-1~deb12u1 | Critical | 6.9% (91st) |
| CVE-2024-6119 | 3.0.11-1~deb12u2 | 3.0.14-1~deb12u2 | High | 14.6% (94th) |

nginx links OpenSSL directly for TLS — the most architecturally relevant dependency for a source build. Compiling nginx against OpenSSL 3.0.15 from upstream (`--with-openssl=...`) is the purest "upstream version bump" and fixes multiple Critical/High CVEs at once.

### Other version-bump candidates

| CVE | Package | Severity | Fixed in | Notes |
|-----|---------|----------|----------|-------|
| CVE-2024-45492 | libexpat1 | Critical | 2.5.0-1+deb12u1 | Integer overflow |
| CVE-2024-37371 | libkrb5 | Critical | 1.20.1-2+deb12u2 | Kerberos |
| CVE-2023-50387 | libsystemd0 | High | 252.23-1~deb12u1 | DNSSEC KeyTrap |

---

## Case 2 — Fix by backporting an upstream patch

The fix exists as a commit in a newer version but not in the one we ship. Cherry-pick it as a `.patch` applied before compiling.

### 2A — libfreetype6 / CVE-2025-27363 *(top candidate)*

Same CVE as 1A, different technique. Debian's `+deb12u4` is itself a backport of specific FreeType upstream commits onto the 2.12.1 tree — we replicate that directly.

**Implementation:** take the diff between `2.12.1+dfsg-5` and `+deb12u4` from salsa.debian.org / the Debian security tracker, save as `build/patches/CVE-2025-27363.patch`, apply at build time.

CVE-2025-27363 can serve as *either* the version-bump (1A) *or* backport (2A) slot. Using it for backport and OpenSSL (1B) for version-bump gives the cleanest separation of techniques.

### 2B — CVE-2026-9256 / nginx *(investigate first)*

| Field | Value |
|-------|-------|
| Package | nginx 1.25.5-1~bookworm |
| Fixed in | Not listed in scan |
| Severity | Critical (Risk 0.2) |

A 2026 CVE with no stable-branch fix likely has a mainline commit (1.27.x+) not yet backported to 1.25.x — a textbook backport if the commit is findable.

**Blocker:** must confirm the fix commit in the nginx changelog / devel list before committing. If unavailable, fall back to 2A or 2C.

### 2C — libexpat1 / CVE-2024-45492 *(clean fallback)*

| Field | Value |
|-------|-------|
| Installed / Fixed | `2.5.0-1` → `2.5.0-1+deb12u1` (Debian) / `2.6.3` (upstream) |
| Severity | Critical · EPSS 2.3% (85th pct) |
| Type | Integer overflow in `XML_GetBuffer` |

Upstream commits for the Aug 2024 overflow group (CVE-2024-45490/45491/45492) are public on GitHub. Apply the 2.6.x commits onto 2.5.0 and rebuild — well-documented and reproducible.

---

## Recommended selection

Two different packages, two different techniques — covering both "nginx dependency built from source" and "OS library patched without waiting for the distro":

| Slot | CVE | Package | Method |
|------|-----|---------|--------|
| **1** | CVE-2024-5535 | openssl | Build nginx against OpenSSL 3.0.15 from source (version bump) |
| **2** | CVE-2025-27363 | libfreetype6 | Backport Debian `deb12u4` patch onto FreeType 2.12.1 source |

---

## Won't-fix CVEs — no action

Documented in `vex.json` as `not_affected`, or `affected` + `response: will_not_fix` with the Debian justification.

| CVE | Package | Reason |
|-----|---------|--------|
| CVE-2013-0337 | nginx | Ancient, low severity, Debian won't fix |
| CVE-2026-42946 | nginx | Won't fix in this Debian release |
| CVE-2023-6277 | libtiff6 | Won't fix |
| CVE-2024-56433 | login/passwd | Won't fix |
| CVE-2023-2953 | libldap-2.5-0 | Won't fix |

---

## Next steps

1. Confirm CVE-2026-9256 upstream fix commit (nginx changelog / mailing list).
2. Lock in the selected pair.
3. Add `build/patches/` entries and update the `Containerfile`.
4. Rescan patched image: `trivy image` + `grype` against `nginx-patched:local`.
5. Diff baseline vs patched and update `README.md` with a before/after table.
6. Populate `vex.json` for the false-positive and won't-fix CVEs.
