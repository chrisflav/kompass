FROM python:3.9-bullseye
RUN mkdir /code
WORKDIR /code
COPY . /code

# uwsgi setup
RUN apt-get install libmariadb-dev
RUN pip install uwsgi
RUN pip install -r requirements.txt
CMD ["uwsgi", "--ini", "/web/kompass.uwsgi.ini"]
