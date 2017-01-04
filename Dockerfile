FROM python:2.7.13-slim

MAINTAINER kdeloach@gmail.com

RUN pip install --upgrade pip
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY api.py /usr/src
COPY getmytime.py /usr/src
COPY getmytime-edit.py /usr/src

WORKDIR /usr/src

ENTRYPOINT ["./getmytime.py"]
