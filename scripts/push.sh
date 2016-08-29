#!/bin/bash

RCol='\e[0m'
Red='\e[0;31m'

docker tag kdeloach/getmytime-cli quay.io/kdeloach/getmytime-cli
docker push quay.io/kdeloach/getmytime-cli

if [ $? -eq 1 ]; then
    echo -e "${Red}Login to quay.io first with: docker login quay.io${RCol}"
fi
