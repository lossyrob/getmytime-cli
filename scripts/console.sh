#!/bin/bash

set -ex

ARGS=$*

docker run -ti --rm \
    -e GETMYTIME_USERNAME=$GETMYTIME_USERNAME \
    -e GETMYTIME_PASSWORD=$GETMYTIME_PASSWORD \
    -v $PWD:/opt \
    --entrypoint bash \
    kdeloach/getmytime-cli
