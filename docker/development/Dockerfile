FROM python:3.9-bullseye

# install additional dependencies
RUN apt-get update && apt-get install -y gettext

WORKDIR /app

# install requirements
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

ARG GID
ARG UID
ARG USER

RUN groupadd -g $GID $USER && useradd -g $GID -u $UID -m -d /app $USER

USER $USER

COPY ./docker /app/docker
