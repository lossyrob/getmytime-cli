FROM python:2.7-slim

MAINTAINER kdeloach@gmail.com

RUN apt-get update && \
    apt-get install -y gcc && \
    apt-get install -y libffi-dev && \
    apt-get install -y libssl-dev

RUN pip install --upgrade pip
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY getmytime.py /opt
WORKDIR /opt

ENTRYPOINT ["./getmytime.py"]
