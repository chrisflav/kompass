# Check if 'dev' is being called with arguments
ifeq (dev,$(firstword $(MAKECMDGOALS)))
  DEV_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  DEV_CMD := $(firstword $(DEV_ARGS))
  DEV_EXTRA_ARGS := $(wordlist 2,$(words $(DEV_ARGS)),$(DEV_ARGS))
  # Create empty targets for extra arguments only (not for DEV_CMD to avoid conflicts)
  $(eval $(DEV_EXTRA_ARGS):;@:)
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
else ifeq ($(DEV_CMD),docs)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd docs && make html"
	@echo ""
	@echo "Generated documentation. To read it, point your browser to:"
	@echo ""
	@echo "file://$$(pwd)/docs/build/html/index.html"
else ifeq ($(DEV_CMD),test)
ifneq ($(keepdb),false)
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd jdav_web && coverage run manage.py test --keepdb $(DEV_EXTRA_ARGS); coverage html"
else
	cd docker/development; USER_ID=$$(id -u) GROUP_ID=$$(id -g) USERNAME=$$(id -un) docker compose exec master bash -c "cd jdav_web && coverage run manage.py test $(DEV_EXTRA_ARGS); coverage html"
endif
	@echo ""
	@echo "Generated coverage report. To read it, point your browser to:"
	@echo ""
	@echo "file://$$(pwd)/jdav_web/htmlcov/index.html"
else
	@echo "Usage: make dev [build|up|down|shell|manage|translate|createsuperuser|docs|test]"
	@echo "  make dev build                        - Build development containers"
	@echo "  make dev build BUILD_ARGS=--no-cache  - Build with docker compose args"
	@echo "  make dev up                           - Start development environment"
	@echo "  make dev up detach=true               - Start in background"
	@echo "  make dev down                         - Stop development environment"
	@echo "  make dev shell                        - Open shell in running container"
	@echo "  make dev translate                    - Generate and compile translation files"
	@echo "  make dev createsuperuser              - Create a superuser account"
	@echo "  make dev docs                         - Build Sphinx documentation"
	@echo "  make dev test [<test-args>]           - Run tests with coverage (keepdb=true by default)"
	@echo "  make dev test keepdb=false [<test-args>] - Run tests without keeping database"
endif

build-test:
	cd docker/test; docker compose build

test-only:
	mkdir -p docker/test/htmlcov
	chmod 777 docker/test/htmlcov
ifeq ($(keepdb), true)
	cd docker/test; DJANGO_TEST_KEEPDB=1 DJANGO_TEST_VERBOSITY=$(or $(verbosity),2) docker compose up --abort-on-container-exit
else
	cd docker/test; DJANGO_TEST_VERBOSITY=$(or $(verbosity),2) docker compose up --abort-on-container-exit
endif
	echo "Generated coverage report. To read it, point your browser to:\n\nfile://$$(pwd)/docker/test/htmlcov/index.html"

# Only execute the test target if it's not being called via 'make dev test'
ifneq (dev,$(firstword $(MAKECMDGOALS)))
test: build-test test-only
else
test:
	@:
endif

# Only execute the docs target if it's not being called via 'make dev docs'
ifneq (dev,$(firstword $(MAKECMDGOALS)))
# No standalone docs target
else
.PHONY: docs
docs:
	@:
endif
