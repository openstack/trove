#!/usr/bin/env bash
set -e

export APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1
APTOPTS="-y -qq --no-install-recommends --allow-unauthenticated"
OS_RELEASE_CODENAME=$(lsb_release -sc)


#
# usage()
#
usage() {
	echo "Usage : $(basename $0) [--datastore datastore] [--datastore-version datastore-version]"
	echo ""
	echo " Command parameters:"
	echo "  'datastore' is the datastore. The options are: 'mariadb', 'mysql', 'postgresql'"
	echo "  'datastore-version' is the datastore version of the datastore."
	echo ""
	exit 1
}


#
# parse options
#
OPT_DATASTORE=""
OPT_DATASTORE_VERSION=""

if [ $# -eq 1 ]; then
	# TODO(hiwkby) We should avoid hardcoding of datastore versions but
	# for compatibility, we must accept the hardcoded version string.
	if [ "$1" = "mysql5.7" ]; then
		OPT_DATASTORE="mysql"
		OPT_DATASTORE_VERSION="5.7"
	elif [ "$1" = "mysql8.0" ]; then
		OPT_DATASTORE="mysql"
		OPT_DATASTORE_VERSION="8.0"
	elif [ "$1" = "mariadb" ]; then
		OPT_DATASTORE="mariadb"
		OPT_DATASTORE_VERSION="10.4"
	elif [ "$1" = "postgresql" ]; then
		OPT_DATASTORE="postgresql"
		OPT_DATASTORE_VERSION="12"
	else
		usage
	fi
else 
	while [ $# -ne 0 ]; do
		if [ -z "$1" ]; then
			break
		elif [ "$1" = "--datastore" ]; then
			shift
			if [ $# -eq 0 ]; then
				echo "\"--datastore\" option should have a datastore name"
				exit 1
			fi
			OPT_DATASTORE="$1"
		elif [ "$1" = "--datastore-version" ]; then
			shift
			if [ $# -eq 0 ]; then
				echo "\"--datastore-version\" option should have a database version"
				exit 1
			fi
			OPT_DATASTORE_VERSION="$1"
		elif [ "$1" = "--help" ]; then
			usage
		fi
		shift
	done
fi

if [ "${OPT_DATASTORE}" = "mysql" ]; then
	if [ "${OPT_DATASTORE_VERSION}" = "5.7" ]; then
		curl -sSL https://repo.percona.com/apt/percona-release_latest.${OS_RELEASE_CODENAME}_all.deb -o percona-release.deb
		dpkg -i percona-release.deb
		percona-release enable-only tools release
		apt-get update
		apt-get install ${APTOPTS} percona-xtrabackup-24
		rm -f percona-release.deb
	elif [ "${OPT_DATASTORE_VERSION}" = "8.0" ]; then
		curl -sSL https://repo.percona.com/apt/percona-release_latest.${OS_RELEASE_CODENAME}_all.deb -o percona-release.deb
		dpkg -i percona-release.deb
		percona-release enable-only tools release
		apt-get update
		apt-get install ${APTOPTS} percona-xtrabackup-80
		rm -f percona-release.deb
	else
		echo "datastore ${OPT_DATASTORE} with ${OPT_DATASTORE_VERSION} not supported"
		exit 1
	fi
elif [ "${OPT_DATASTORE}" = "mariadb" ]; then
	# See the url below about the supported version.
	# https://mariadb.com/docs/xpand/ref/repo/cli/mariadb_repo_setup/mariadb-server-version/
	apt-key adv --fetch-keys 'https://mariadb.org/mariadb_release_signing_key.asc'
	if $(curl -LsS -O https://downloads.mariadb.com/MariaDB/mariadb_repo_setup); then
		if [ -f "./mariadb_repo_setup" ]; then
			chmod u+x "./mariadb_repo_setup"
			if $(./mariadb_repo_setup --mariadb-server-version=${OPT_DATASTORE_VERSION}); then
				apt-get install ${APTOPTS} mariadb-backup
			else
				echo "mariadb_repo_setup command failed"
				exit 1
			fi
		else
			echo "no such a script mariadb_repo_setup"
			exit 1
		fi
	else
		echo "curl command failed"
		exit 1
	fi
elif [ "${OPT_DATASTORE}" = "postgresql" ]; then
	# See here for the supported version
	# https://www.postgresql.org/support/versioning/
	apt-key adv --fetch-keys 'https://www.postgresql.org/media/keys/ACCC4CF8.asc'
	add-apt-repository "deb [arch=amd64] http://apt.postgresql.org/pub/repos/apt/ ${OS_RELEASE_CODENAME}-pgdg main"

	# postgresql-client-{6,7,8,9}.x or postgresql-client-{10,11,12}
	DATASTORE_CLIENT_PKG_VERSION=$(echo ${OPT_DATASTORE_VERSION} | awk -F'.' '{ if ($1 > 9) {print $1} else {print $1 "." $2} }')
	if [ -z "${DATASTORE_CLIENT_PKG_VERSION}" ]; then
		echo "no postgresql-client version"
		exit 1
	fi
	apt-get install ${APTOPTS} postgresql-client-${DATASTORE_CLIENT_PKG_VERSION}
fi

apt-get clean
rm -rf /var/lib/apt/lists/*
