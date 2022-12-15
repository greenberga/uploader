FROM python:3.11

ADD . /app
WORKDIR /app

RUN pip install pipenv
RUN pipenv install -d

ENTRYPOINT /bin/bash
