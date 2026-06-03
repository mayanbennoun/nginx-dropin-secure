#!/usr/bin/env bash

# Exit immediately on failure
set -e

cd "$(dirname "$0")"

NGINX_VERSION="1.25.5"
TARBALL_DIR="sources"
TARBALL_PATH="${TARBALL_DIR}/nginx-${NGINX_VERSION}.tar.gz"
WORK_DIR="nginx-${NGINX_VERSION}"

echo "==> Step 1: Preparing directories..."
mkdir -p "$TARBALL_DIR"
mkdir -p dist

echo "==> Step 2: Downloading upstream NGINX ${NGINX_VERSION} source..."
# Only download if we haven't already
if [ ! -f "${TARBALL_DIR}/nginx-${NGINX_VERSION}-upstream.tar.gz" ]; then
    curl -o "${TARBALL_DIR}/nginx-${NGINX_VERSION}-upstream.tar.gz" http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz
fi

echo "==> Step 3: Extracting source and applying CVE patches..."
# Clean up any leftover work directory from previous runs
rm -rf "$WORK_DIR"
tar -xzf "${TARBALL_DIR}/nginx-${NGINX_VERSION}-upstream.tar.gz"

# Iterate through the patches directory and apply any .patch files found
if [ -d "patches" ] && [ "$(ls -A patches/*.patch 2>/dev/null)" ]; then
    for patch_file in patches/*.patch; do
        echo "    -> Applying ${patch_file}..."
        # Apply the patch using -p1 (standard for git-generated patches)
        patch -d "$WORK_DIR" -p1 < "$patch_file"
    done
else
    echo "    -> No patches found in patches/ directory. Building vanilla NGINX."
fi

echo "==> Step 4: Creating the patched source tarball..."
# Package the patched source into the format Dockerfile.build expects
tar -czf "$TARBALL_PATH" "$WORK_DIR"
rm -rf "$WORK_DIR" # Clean up the uncompressed folder to save space

echo "==> Step 5: Building the Docker image..."
docker build \
  -f Dockerfile.build \
  --build-arg NGINX_SOURCE_TARBALL="$TARBALL_PATH" \
  -t nginx-deb-build .

echo "==> Step 6: Extracting the compiled .deb packages..."
container_id="$(docker create nginx-deb-build)"
docker cp "$container_id":/out/. dist/
docker rm "$container_id"

echo "==> Success! Your patched NGINX .deb packages are ready in the 'build/dist/' directory."
ls -lh dist/