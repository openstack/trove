#!/usr/bin/env bash
# Arguments: if given the first argument is the location of a pid file.
if [ $# -lt 1 ]; then
    export PID_FILE=".pid"
else
    export PID_FILE=$1
fi
if [ -f $PID_FILE ];
then
    cat $PID_FILE
    kill `cat $PID_FILE`
    echo "Stopping server."
    rm $PID_FILE
else
    echo "pid file not found."
fi
