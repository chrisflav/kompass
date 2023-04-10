build-test:
	cd docker/test; docker compose build

test:
	cd docker/test; docker compose up --abort-on-container-exit
