FROM python:3.9-bullseye

# install additional dependencies
RUN apt-get update && apt-get install -y gettext texlive texlive-fonts-extra

# create user
RUN groupadd -g 501 app && useradd -g 501 -u 501 -m -d /app app

# create static directory and set permissions, when doing this before mounting a named volume
# in docker-compose.yaml, the permissions are inherited during the mount.
RUN mkdir -p /var/www/jdav_web/assets && chown -R app:app /var/www/jdav_web/assets

# create static directory and set permissions, when doing this before mounting a named volume
# in docker-compose.yaml, the permissions are inherited during the mount.
RUN mkdir -p /tmp/uwsgi && chown -R app:app /tmp/uwsgi

WORKDIR /app
USER app

# add .local/bin to PATH
ENV PATH="/app/.local/bin:$PATH"

# install requirements
COPY --chown=app:app ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# for production, install uwsgi
RUN pip install uwsgi

COPY --chown=app:app . /app
