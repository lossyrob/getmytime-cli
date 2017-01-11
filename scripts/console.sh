#!/bin/bash

set -ex

ARGS=$*

# NOTE: Ignore the hamster stuff if you don't care about sync.sh

HAMSTER_DB_GUEST=/usr/db/hamster.db
HAMSTER_DB_HOST=~/.local/share/hamster-applet/hamster.db
HAMSTER_PATH=/var/projects/hamster-getmytime/

docker run -ti --rm \
    -e GETMYTIME_USERNAME=$GETMYTIME_USERNAME \
    -e GETMYTIME_PASSWORD=$GETMYTIME_PASSWORD \
    -e HAMSTER_DB=$HAMSTER_DB_GUEST \
    -v $PWD:/usr/src \
    -v $HAMSTER_DB_HOST:$HAMSTER_DB_GUEST \
    -v $HAMSTER_PATH:/usr/hamster \
    --entrypoint bash \
    kdeloach/getmytime-cli
