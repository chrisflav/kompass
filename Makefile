build-test:
	cd docker/test; docker compose build

test:
	touch docker/test/coverage.xml
	chmod 666 docker/test/coverage.xml
	cd docker/test; docker compose up --abort-on-container-exit
	sed -i 's/\/app\/jdav_web/jdav_web/g' docker/test/coverage.xml
