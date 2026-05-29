# CVE Triage Hypothesis — nginx:1.25-bookworm

## Image metadata (confirmed via docker inspect)

| Field            | Value                                                              |
|------------------|--------------------------------------------------------------------|
| Tag              | `nginx:1.25-bookworm`                                              |
| Image ID         | `sha256:e784f4560448b14a66f55c26e1b4dad2c2877cc73d001b7cd0b18e24a700a070` |
| Digest           | `nginx@sha256:a484819eb60211f5299034ac80f6a681b06f89e65866ce91f356ed7c72af059c` |
| NGINX_VERSION    | **1.25.5**                                                         |
| PKG_RELEASE      | `1~bookworm`                                                       |
| NJS_VERSION      | `0.8.4`                                                            |
| Build date       | 2024-05-03T19:49:21Z                                               |
| Architecture     | amd64                                                              |
| OS               | Debian Bookworm                                                    |

Scanners: Trivy + Grype, run against the image above before any patching.

---

## Scanner summary

| Scanner | Total CVEs found | Notable HIGH/CRITICAL |
|---------|------------------|-----------------------|
| Grype   | 472 rows         | 2 KEV-listed, 8 Critical, 15+ High |
| Trivy   | Full JSON (see baseline-trivy.txt) | Corroborates Grype findings |

The two KEV-listed CVEs (Known Exploited Vulnerabilities — actively exploited in the wild):
- **CVE-2025-27363** — libfreetype6 (Risk 81.9, EPSS 70.8%)
- **CVE-2023-44487** — nginx Debian package (Risk 78.8, EPSS 94.4%)

---

## Critical fact: nginx 1.25.5 and CVE-2023-44487

CVE-2023-44487 is the HTTP/2 Rapid Reset attack. The nginx changelog shows the fix was
released in nginx **1.25.3** (October 19, 2023). Since we are shipping **1.25.5** (released
March 2024), the fix is already present in the upstream source tarball we compile from.

The scanner flags it because the Debian package `1.25.5-1~bookworm` never received a
Debian Security Advisory (DSA) — the Debian packaging team did not issue one because the
official nginx.org mainline packages already contained the fix. When we build nginx 1.25.5
from the upstream tarball, the vulnerability does not exist in the compiled binary.

**Consequence for CVE selection:**
- CVE-2023-44487 is NOT a valid backport target for nginx 1.25.5 — the fix is already
  in the source.
- It IS a demonstration of why building from source beats using the Debian repackaged
  binary: the compiled output is clean even though the package metadata triggers the scanner.
- It can be documented in `vex.json` as "not affected — fix present in upstream source
  at 1.25.3, shipping 1.25.5."

---

## Case 1 — Candidates: fix by version bump of a dependency

A version bump means updating a system library or upstream source to a version that
contains the fix, without manually patching source code.

### Candidate 1A — libfreetype6 / CVE-2025-27363 (PRIMARY PICK)

| Field          | Value                              |
|----------------|------------------------------------|
| Package        | libfreetype6                       |
| Installed      | 2.12.1+dfsg-5                      |
| Fixed in       | 2.12.1+dfsg-5+deb12u4              |
| Severity       | High                               |
| EPSS           | 70.8% (98th percentile)            |
| Risk score     | **81.9 — highest in the scan**     |
| KEV listed     | Yes                                |
| CVE type       | Out-of-bounds write in FreeType    |

**Why this is the top pick:**
- Only CVE in the scan with a risk score above 10 — by a large margin.
- KEV-listed means real attackers are using this right now.
- Fix is unambiguous: pin or upgrade a single package.
- Before/after scanner diff will be clean and easy to demonstrate.

**Implementation:** In the Containerfile, after the base image layer:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6=2.12.1+dfsg-5+deb12u4 \
    && rm -rf /var/lib/apt/lists/*
```

---

### Candidate 1B — OpenSSL / CVE-2024-5535 + CVE-2024-6119 (STRONG ALTERNATIVE)

| Field          | CVE-2024-5535        | CVE-2024-6119        |
|----------------|----------------------|----------------------|
| Package        | libssl3 / openssl    | libssl3 / openssl    |
| Installed      | 3.0.11-1~deb12u2     | 3.0.11-1~deb12u2     |
| Fixed in       | 3.0.15-1~deb12u1     | 3.0.14-1~deb12u2     |
| Severity       | Critical             | High                 |
| EPSS           | 6.9% (91st)          | 14.6% (94th)         |

**Why this is a strong alternative:**
- nginx directly links against OpenSSL for TLS — this is architecturally the most
  relevant dependency for a source build.
- Building nginx against OpenSSL 3.0.15 from upstream source (instead of system 3.0.11)
  is the purest "upstream source version bump" for a build-from-source workflow.
- Fixes multiple Critical/High OpenSSL CVEs in a single operation.

**Implementation:** In the build stage, download and compile OpenSSL 3.0.15 from source,
then pass `--with-openssl=/path/to/openssl-3.0.15` when configuring nginx.

---

### Other notable version bump candidates

| CVE             | Package            | Severity | Fixed in                 | Notes              |
|-----------------|--------------------|----------|--------------------------|--------------------|
| CVE-2024-45492  | libexpat1          | Critical | 2.5.0-1+deb12u1          | Integer overflow   |
| CVE-2024-37371  | libkrb5/krb5       | Critical | 1.20.1-2+deb12u2         | Kerberos           |
| CVE-2023-50387  | libsystemd0        | High     | 252.23-1~deb12u1         | DNSSEC KeyTrap     |
| CVE-2024-6119   | openssl            | High     | 3.0.14-1~deb12u2         | Bundled with 1B    |

---

## Case 2 — Candidates: fix by backporting a patch from upstream

A backport means: the fix exists as a commit in a newer upstream version (or mainline),
but not in the exact version we are shipping. We cherry-pick that commit and apply it as
a `.patch` file to our source tree before compiling.

### Candidate 2A — libfreetype6 / CVE-2025-27363 — backport angle (PRIMARY PICK)

Same CVE as 1A, but approached differently. The Debian fix `+deb12u4` is itself a
backport — Debian's security team took specific commits from FreeType's upstream repo
and applied them to the 2.12.1 source tree. We replicate that process directly.

| Field          | Value                                                       |
|----------------|-------------------------------------------------------------|
| Shipped version | FreeType 2.12.1 (libfreetype6 2.12.1+dfsg-5)              |
| Upstream fix   | Commits in FreeType 2.13.x / mainline                       |
| Backport path  | Clone FreeType 2.12.1 source, apply the specific upstream   |
|                | commit(s) Debian used for deb12u4, build patched library    |
| Why compelling | KEV-listed; demonstrates the full patch-from-source         |
|                | workflow independent of the distro release cycle            |

**Implementation:** Obtain the diff between `2.12.1+dfsg-5` and `2.12.1+dfsg-5+deb12u4`
from the Debian security tracker or salsa.debian.org, save as `build/patches/CVE-2025-27363.patch`,
apply during build.

Note: CVE-2025-27363 can serve as EITHER the version-bump fix (1A) OR the backport fix
(2A) depending on which implementation path is chosen. Using it for the backport slot and
using OpenSSL (1B) for the version-bump slot gives the cleanest separation of techniques.

---

### Candidate 2B — CVE-2026-9256 / nginx (INVESTIGATE BEFORE COMMITTING)

| Field          | Value                                      |
|----------------|--------------------------------------------|
| Package        | nginx 1.25.5-1~bookworm                    |
| Fixed in       | Not listed (no fix version in scan)        |
| Severity       | Critical                                   |
| Risk score     | 0.2                                        |

**Why it fits "backport":** A 2026 CVE with no fix version in the 1.25.x stable branch
likely has a fix commit in nginx mainline (1.27.x or later) that has not been backported
to the stable 1.25.x series. If the upstream commit is findable, this is a textbook
backport scenario: apply the mainline commit as a patch to 1.25.5 source.

**Blocker:** The fix commit must be confirmed in the nginx changelog or nginx-devel mailing
list before this can be implemented. If no upstream commit is publicly available yet,
fall back to 2A (libfreetype6 backport) or 2C below.

---

### Candidate 2C — libexpat1 / CVE-2024-45492 (CLEAN FALLBACK)

| Field          | Value                                            |
|----------------|--------------------------------------------------|
| Package        | libexpat1                                        |
| Installed      | 2.5.0-1                                          |
| Fixed in       | 2.5.0-1+deb12u1 (Debian) / 2.6.3 (upstream)     |
| Severity       | Critical                                         |
| EPSS           | 2.3% (85th percentile)                           |
| CVE type       | Integer overflow in XML_GetBuffer                |

**Why it works as a backport:** The upstream libexpat fix commits for the August 2024
integer overflow group (CVE-2024-45490, 45491, 45492) are publicly available in the
libexpat GitHub repository. We ship 2.5.0, apply the specific commits from 2.6.x as a
patch, and rebuild. Well-documented, reproducible, and verifiable.

---

## Final selection and rationale

| Slot   | CVE              | Package        | Method                          | Rationale                                   |
|--------|------------------|----------------|---------------------------------|---------------------------------------------|
| **1**  | **CVE-2025-27363** | libfreetype6 | apt version pin to deb12u4     | KEV-listed, highest risk score in scan (81.9)|
| **2**  | **CVE-2025-27363** | libfreetype6 | Backport upstream patch to 2.12.1 | Same CVE, different implementation; OR swap for OpenSSL 3.0.15 build |

Cleaner separation of techniques — recommended pair:

| Slot | CVE              | Package        | Method                                       |
|------|------------------|----------------|----------------------------------------------|
| **1** | CVE-2024-5535   | openssl        | Build nginx against OpenSSL 3.0.15 from source (upstream version bump) |
| **2** | CVE-2025-27363  | libfreetype6   | Backport Debian deb12u4 patch onto FreeType 2.12.1 source |

This pair uses two different packages, two different techniques, and covers both the
"nginx dependency built from source" angle and the "OS library patched without waiting
for the distro" angle.

---

## CVE-2023-44487 disposition (nginx — HTTP/2 Rapid Reset)

| Field      | Value                                                               |
|------------|---------------------------------------------------------------------|
| Status     | **Not affected in our build** — fix present in nginx 1.25.3+       |
| Evidence   | nginx 1.25.5 upstream tarball contains the 1.25.3 HTTP/2 fix       |
| Scanner    | Flags the Debian package due to missing DSA, not the binary         |
| Action     | Document in `vex.json`: `status: not_affected`, `justification:    |
|            | vulnerable_code_not_present`, note that we build from upstream      |
|            | 1.25.5 source which includes the fix from 1.25.3                   |

---

## Packages marked "won't fix" — no action required

| CVE             | Package       | Reason for no action                        |
|-----------------|---------------|---------------------------------------------|
| CVE-2013-0337   | nginx         | Ancient, low severity, Debian will not fix  |
| CVE-2026-42946  | nginx         | Won't fix in this Debian release            |
| CVE-2023-6277   | libtiff6      | Won't fix                                   |
| CVE-2024-56433  | login/passwd  | Won't fix                                   |
| CVE-2023-2953   | libldap-2.5-0 | Won't fix                                   |

These will be documented in `vex.json` with `status: not_affected` or `status: affected`
with `response: will_not_fix` and the Debian maintainer justification.

---

## Next steps

1. Confirm CVE-2026-9256 upstream fix commit availability (nginx changelog / mailing list).
2. Choose final pair from the table above.
3. Create `build/patches/` entries and update `Containerfile`.
4. Run patched image scan: `trivy image` + `grype` against `nginx-patched:local`.
5. Diff CVE lists (baseline vs patched) and update `README.md` with before/after table.
6. Populate `vex.json` for remaining / won't-fix CVEs.
