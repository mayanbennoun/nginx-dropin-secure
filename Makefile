.PHONY: all build-deb image test

IMAGE = nginx-patched:1.25.5
VENV = test/.venv

all: build-deb image test

build-deb:
	bash build/build.sh

image: build-deb
	docker build -f Containerfile -t $(IMAGE) .

$(VENV)/bin/pytest: test/requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r test/requirements.txt

test: image $(VENV)/bin/pytest
	$(VENV)/bin/pytest test/ -v -s
