GITCOMMIT := $(shell git rev-parse --short=7 HEAD)
DOCKERIMAGE := $(shell cat .docker-image)
PWD := $(shell pwd)

docker-image:
	docker build -t uploader:$(GITCOMMIT) .
	echo $(GITCOMMIT) > .docker-image

run-docker:
	docker run --rm -it -v $(PWD):/app -w /app -p 5000:5000 uploader:$(DOCKERIMAGE)

.PHONY: docker-image
