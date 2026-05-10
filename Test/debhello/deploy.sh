#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
TOP_DIR="${DIR}"

BUILD_CONTAINER_FOCAL="pbuilder-container-focal:latest"

# docker run \
#       --network=host \
#       --workdir=/home/build-user/s \
#       --rm \
#       -v $TOP_DIR:/home/build-user/s \
#       -v $TOP_DIR/Build/pbuilder/focal:/var/cache/pbuilder/result \
#       $BUILD_CONTAINER_FOCAL \
#       upload_signed_package.sh

docker run -it \
      --network=host \
      --workdir=/home/build-user/s \
      --rm \
      -v $TOP_DIR:/home/build-user/s \
      -v $TOP_DIR/Build/pbuilder/focal:/var/cache/pbuilder/result \
      $BUILD_CONTAINER_FOCAL \
      /bin/bash


