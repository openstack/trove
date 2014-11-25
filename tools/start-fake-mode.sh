#!/usr/bin/env bash
# Arguments: Use --pid_file to specify a pid file location.


if [ ! -d ".tox/py27" ]; then
    tox -epy27
fi

function run() {
    .tox/py27/bin/python $@
}
run bin/trove-manage \
    --config-file=etc/trove/trove.conf.test db_recreate \
    trove_test.sqlite mysql fake
run bin/trove-fake-mode \
    --fork --config-file=etc/trove/trove.conf.test \
    $@

