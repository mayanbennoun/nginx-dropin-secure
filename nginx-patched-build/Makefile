.PHONY: all build-deb image test

IMAGE = nginx-patched:1.25.5
CONTAINER = nginx-test

all: build-deb image test

build-deb:
	bash build/build.sh

image: build-deb
	docker build -f Containerfile -t $(IMAGE) .

test: image
	docker run -d -p 8080:80 --name $(CONTAINER) $(IMAGE)
	test/.venv/bin/pytest test/ -v || (docker stop $(CONTAINER) && docker rm $(CONTAINER) && exit 1)
	docker stop $(CONTAINER)
	docker rm $(CONTAINER)
