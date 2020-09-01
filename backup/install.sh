#!/usr/bin/env bash
set -e

APTOPTS="-y -qq --no-install-recommends --allow-unauthenticated"

case "$1" in
"mysql")
    curl -sSL https://repo.percona.com/apt/percona-release_latest.$(lsb_release -sc)_all.deb -o percona-release.deb
    dpkg -i percona-release.deb
    percona-release enable-only tools release
    apt-get update
    apt-get install $APTOPTS percona-xtrabackup-$2
    apt-get clean
    ;;
"mariadb")
    apt-key adv --fetch-keys 'https://mariadb.org/mariadb_release_signing_key.asc'
    add-apt-repository "deb [arch=amd64] http://mirror2.hs-esslingen.de/mariadb/repo/10.4/ubuntu $(lsb_release -cs) main"
    apt-get update
    apt-get install $APTOPTS mariadb-backup
    apt-get clean
    ;;
*)
    echo "datastore $1 not supported"
    exit 1
    ;;
esac
