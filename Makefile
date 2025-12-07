# Check if 'dev' is being called with arguments
ifeq (dev,$(firstword $(MAKECMDGOALS)))
  DEV_CMD := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(DEV_CMD):;@:)
endif

dev:
ifeq ($(DEV_CMD),build)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose build $(BUILD_ARGS)
else ifeq ($(DEV_CMD),up)
ifeq ($(detach), true)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose up -d
else
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose up
endif
else ifeq ($(DEV_CMD),down)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose down
else ifeq ($(DEV_CMD),shell)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd jdav_web && bash"
else ifeq ($(DEV_CMD),translate)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd jdav_web && python3 manage.py makemessages --locale de --no-location --no-obsolete && python3 manage.py compilemessages"
else ifeq ($(DEV_CMD),createsuperuser)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd jdav_web && python3 manage.py createsuperuser"
else
	@echo "Usage: make dev [build|up|down|shell|manage|translate|createsuperuser]"
	@echo "  make dev build                        - Build development containers"
	@echo "  make dev build BUILD_ARGS=--no-cache  - Build with docker compose args"
	@echo "  make dev up                           - Start development environment"
	@echo "  make dev up detach=true               - Start in background"
	@echo "  make dev down                         - Stop development environment"
	@echo "  make dev shell                        - Open shell in running container"
	@echo "  make dev translate                    - Generate and compile translation files"
	@echo "  make dev createsuperuser              - Create a superuser account"
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
