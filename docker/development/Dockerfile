FROM python:3.9-bullseye

# install additional dependencies
RUN apt-get update && apt-get install -y gettext

WORKDIR /app

# install requirements
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY ./docker /app/docker
