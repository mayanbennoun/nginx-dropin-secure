# nginx Debian build

Create `sources/nginx-1.25.5.tar.gz` from your nginx source. It must unpack to
`nginx-1.25.5/`.

```sh
mkdir -p sources
git -C /path/to/nginx archive --format=tar.gz --prefix=nginx-1.25.5/ -o "$PWD/sources/nginx-1.25.5.tar.gz" HEAD
```

Build the image:

```sh
docker build \
  -f Dockerfile.build \
  --build-arg NGINX_SOURCE_TARBALL=sources/nginx-1.25.5.tar.gz \
  -t nginx-deb-build .
```

Copy the generated Debian packages out:

```sh
container_id="$(docker create nginx-deb-build)"
mkdir -p dist
docker cp "$container_id":/out/. dist/
docker rm "$container_id"
```

The `.deb` files will be in `dist/`.
