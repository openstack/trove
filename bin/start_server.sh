#!/usr/bin/env bash
# Arguments: Use --pid_file to specify a pid file location.


if [ ! -d ".tox/py26" ]; then
    tox -epy26
fi

function run() {
    .tox/py26/bin/python $@
}
run bin/trove-manage \
    --config-file=etc/trove/trove.conf.test db_wipe \
    trove_test.sqlite mysql fake
run bin/trove-server \
    --fork --config-file=etc/trove/trove.conf.test \
    $@

