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
