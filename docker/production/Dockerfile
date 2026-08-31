FROM python:3.13-trixie

# install additional dependencies
RUN apt-get update && apt-get install -y gettext texlive texlive-fonts-extra pandoc

# create user
RUN groupadd -g 501 app && useradd -g 501 -u 501 -m -d /app app

# create static directory and set permissions, when doing this before mounting a named volume
# in docker-compose.yaml, the permissions are inherited during the mount.
RUN mkdir -p /var/www/jdav_web/static && chown -R app:app /var/www/jdav_web/static

# create media directory and set permissions, so that the celery worker can render PDFs
# here in deployments that do not mount anything over it. Where ./media is bind mounted in
# docker-compose.yaml, the ownership of the host directory applies instead.
RUN mkdir -p /var/www/jdav_web/media && chown -R app:app /var/www/jdav_web/media

# create static directory and set permissions, when doing this before mounting a named volume
# in docker-compose.yaml, the permissions are inherited during the mount.
RUN mkdir -p /tmp/uwsgi && chown -R app:app /tmp/uwsgi

WORKDIR /app
USER app

# add .local/bin to PATH
ENV PATH="/app/.local/bin:$PATH"

# install requirements
COPY --chown=app:app ./pyproject.toml ./uv.lock /app/
RUN pip install uv && uv export -o requirements.txt && pip install -r requirements.txt

COPY --chown=app:app . /app
