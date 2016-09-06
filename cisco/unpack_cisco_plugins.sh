#!/bin/bash
#
# Copyright 2015 Cisco Systems Inc.

# set -x 

UNPACKED_DIR="$(dirname "${BASH_SOURCE[0]}")"
DEST_DIR=/opt/rally/plugins/cisco

COMMON=common
PLUGINS=plugins
SCENARIOS=scenarios
SCENARIO_DIR=${DEST_DIR}/${SCENARIOS}

mkdir -p ${DEST_DIR}
rm -rf ${DEST_DIR}/*

rsync -a ${UNPACKED_DIR}/${COMMON} ${DEST_DIR}/
rsync -a ${UNPACKED_DIR}/${PLUGINS} ${DEST_DIR}/
rsync -a ${UNPACKED_DIR}/${SCENARIOS} ${DEST_DIR}/

echo "To test scenarios, run one of the next command:"
echo ""

tasks=`find ${SCENARIO_DIR} -type f | egrep "\.(json|yaml)$"`
command="rally task start --task "
for task in ${tasks}
do
    echo ${command} ${task}
done
