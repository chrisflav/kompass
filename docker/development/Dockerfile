FROM python:3.9-bookworm

# install additional dependencies
RUN apt-get update && apt-get install -y gettext texlive texlive-fonts-extra pandoc

WORKDIR /app

# install requirements
COPY ./requirements.txt /app/requirements.txt
RUN pip install coverage -r requirements.txt

ARG GID
ARG UID
ARG USER

RUN if ! getent group $GID > /dev/null 2>&1; then \
        groupadd -g $GID $USER; \
    fi && \
    useradd -g $GID -u $UID -m -d /app $USER

USER $USER

COPY ./docker /app/docker
