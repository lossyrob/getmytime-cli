FROM python:2.7.13-slim

MAINTAINER kdeloach@gmail.com

RUN apt-get update && apt-get install -y \
    build-essential libssl-dev libffi-dev python-dev gcc

RUN pip install --upgrade pip
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY api.py /usr/src
COPY getmytime.py /usr/src
COPY getmytime-edit.py /usr/src

WORKDIR /usr/src

ENTRYPOINT ["./getmytime.py"]
