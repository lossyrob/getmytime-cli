#!/bin/bash

# Find latest timesheet record on getmytime.com and import all
# hamster records since then.

# NOTE: Because getmytime.com does not store time fields, we can only
# sync entries by day. If the latest record on getmytime.com is 1/1/2016,
# this script will only attempt to sync records starting from 1/2/2016.

ARGS=$*

SCRIPTS=$(dirname $0)
HAMSTER=$SCRIPTS/../../hamster-getmytime/hamster.py
GETMYTIME=$SCRIPTS/../getmytime.py

latest_entry_date() {
    i=0

    # Fetch getmytime.com entries 1 week at a time to find the
    # latest entry date.
    while true; do
        result=$($SCRIPTS/run.sh ls --tmpl "{entry_date:%Y-%m-%d}" $(date -d "-$i week" +"%Y-%m-%d") | tail -n 1)

        if [[ "$result" != "" ]] ; then
            echo $result
            break
        fi

        # Abort script if ctrl+c is pressed.
        if [[ "$result" == *KeyboardInterrupt* ]] ; then
            exit 1
        fi

        i=$[$i+1]
    done
}

echo "Checking for latest getmytime.com entry..."

dt=$(latest_entry_date)
echo "Latest entry date found is ${dt}"

# Increase latest entry by 1 day so we don't upload duplicate entries.
dt=$(date -d "$dt + 1 day" +"%Y-%m-%d")
echo "Uploading entries from $dt until now"

$HAMSTER $dt | $GETMYTIME import $ARGS
