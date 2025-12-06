# Check if 'dev' is being called with arguments
ifeq (dev,$(firstword $(MAKECMDGOALS)))
  DEV_CMD := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(DEV_CMD):;@:)
endif

dev:
ifeq ($(DEV_CMD),build)
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose build
else ifeq ($(DEV_CMD),up)
ifeq ($(detach), true)
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose up -d
else
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose up
endif
else ifeq ($(DEV_CMD),down)
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose down
else ifeq ($(DEV_CMD),shell)
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose exec master bash
else ifeq ($(firstword $(DEV_CMD)),manage)
	cd docker/development; UID=$$(id -u) GID=$$(id -g) USER=$$(id -un) docker compose exec master bash -c "cd jdav_web && python3 manage.py $(wordlist 2,$(words $(DEV_CMD)),$(DEV_CMD))"
else
	@echo "Usage: make dev [build|up|down|shell|manage]"
	@echo "  make dev build              - Build development containers"
	@echo "  make dev up                 - Start development environment"
	@echo "  make dev up detach=true     - Start in background"
	@echo "  make dev down               - Stop development environment"
	@echo "  make dev shell              - Open shell in running container"
	@echo "  make dev manage <command>   - Run Django management command"
	@echo "                                (e.g., make dev manage migrate)"
endif

build-test:
	cd docker/test; docker compose build

test-only:
	mkdir -p docker/test/htmlcov
	chmod 777 docker/test/htmlcov
ifeq ($(keepdb), true)
	cd docker/test; DJANGO_TEST_KEEPDB=1 docker compose up --abort-on-container-exit
else
	cd docker/test; docker compose up --abort-on-container-exit
endif
	echo "Generated coverage report. To read it, point your browser to:\n\nfile://$$(pwd)/docker/test/htmlcov/index.html"

test: build-test test-only
