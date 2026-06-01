# nginx-patched-build

Build pipeline for producing a patched nginx image with CVE remediation and compatibility verification.

## Directory layout

```
nginx-patched-build/
├── build/
│   ├── Dockerfile.build   # Build-stage Dockerfile
│   ├── build.sh           # Build script
│   └── patches/
│       └── CVE-202X-XXXX.patch
├── test/
│   ├── test_compat.py     # Compatibility tests
│   └── Makefile           # Test runner
├── Containerfile          # Final runtime image
├── vex.json               # VEX (Vulnerability Exploitability eXchange) metadata
└── README.md
```

## Python 3.14 (WSL / pyenv)

Compatibility tests use **Python 3.14** via [pyenv](https://github.com/pyenv/pyenv). Debian’s system `python3` stays on 3.13; pyenv installs 3.14 alongside it.

From **Debian WSL** (not `docker-desktop`):

```bash
cd /mnt/c/Users/Mayan/echo-assignment/nginx-patched-build/test
bash setup-pyenv.sh
```

That script installs build deps, pyenv, Python `3.14.0`, and a venv at `~/venvs/nginx-patched-build-314` (avoids creating `.venv` on `/mnt/c`, which often fails in WSL).

After setup, activate the venv:

```bash
source ~/venvs/nginx-patched-build-314/bin/activate
```

`test/.python-version` pins `3.14.0` for `pyenv local` in that directory.

## Usage

1. Add the CVE patch under `build/patches/`.
2. Run the build via `build/build.sh` or the build Dockerfile.
3. Build the runtime image from `Containerfile`.
4. Run compatibility tests from `test/` (with the venv active).

## Security scanning

Baseline and patched image scans (Trivy + Grype), triage, and documentation: [docs/CVE-SCANNING-WORKFLOW.md](docs/CVE-SCANNING-WORKFLOW.md).
