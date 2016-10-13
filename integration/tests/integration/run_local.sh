#!/usr/bin/env bash
# Specify the path to the Trove repo as argument one.
# This script will create a .pid file and report in the current directory.

set -e
if [ $# -lt 1 ]; then
    echo "Please give the path to the Trove repo as argument one."
    exit 5
else
    TROVE_PATH=$1
fi
if [ $# -lt 2 ]; then
    echo "Please give the path to the Trove Client as argument two."
    exit 5
else
    TROVECLIENT_PATH=$2
fi
shift;
shift;


PID_FILE="`pwd`.pid"

function start_server() {
    pushd $TROVE_PATH
    bin/start_server.sh --pid_file=$PID_FILE
    popd
}

function stop_server() {
    if [ -f $PID_FILE ];
    then
        pushd $TROVE_PATH
        bin/stop_server.sh $PID_FILE
        popd
    else
        echo "The pid file did not exist, so not stopping server."
    fi
}
function on_error() {
    echo "Something went wrong!"
    stop_server
}

trap on_error EXIT  # Proceed to trap - END in event of failure.

TROVE_CLIENT_PATH=$TROVECLIENT_PATH tox -e py26
start_server
.tox/py26/bin/pip install -U $TROVECLIENT_PATH
PYTHONPATH=$PYTHONPATH:$TROVECLIENT_PATH .tox/py26/bin/python int_tests.py \
    --conf=localhost.test.conf -- $@
stop_server


trap - EXIT
echo "Ran tests successfully. :)"
exit 0
