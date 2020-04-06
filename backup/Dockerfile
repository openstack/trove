FROM ubuntu:18.04
LABEL maintainer="anlin.kong@gmail.com"

ARG APTOPTS="-y -qq --no-install-recommends --allow-unauthenticated"
ARG PERCONA_XTRABACKUP_VERSION=24
ENV DEBIAN_FRONTEND noninteractive
ENV APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1

RUN apt-get update \
    && apt-get install $APTOPTS gnupg2 lsb-release apt-utils apt-transport-https ca-certificates software-properties-common curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install percona-xtrabackup for mysql
RUN curl -sSL https://repo.percona.com/apt/percona-release_latest.$(lsb_release -sc)_all.deb -o percona-release.deb \
    && dpkg -i percona-release.deb \
    && percona-release enable-only tools release \
    && apt-get update \
    && apt-get install $APTOPTS percona-xtrabackup-${PERCONA_XTRABACKUP_VERSION} \
    && apt-get clean

# Install mariabackup for mariadb
Run apt-key adv --fetch-keys 'https://mariadb.org/mariadb_release_signing_key.asc' \
    && add-apt-repository "deb [arch=amd64] http://mirror2.hs-esslingen.de/mariadb/repo/10.4/ubuntu $(lsb_release -cs) main" \
    && apt-get update \
    && apt-get install $APTOPTS mariadb-backup \
    && apt-get clean

RUN apt-get update \
    && apt-get install $APTOPTS build-essential python3-setuptools python3-all python3-all-dev python3-pip libffi-dev libssl-dev libxml2-dev libxslt1-dev libyaml-dev \
    && apt-get clean

COPY . /opt/trove/backup
WORKDIR /opt/trove/backup

RUN pip3 --no-cache-dir install -U -r requirements.txt

RUN curl -sSL https://github.com/Yelp/dumb-init/releases/download/v1.2.2/dumb-init_1.2.2_amd64 -o /usr/local/bin/dumb-init \
    && chmod +x /usr/local/bin/dumb-init

ENTRYPOINT ["dumb-init", "--single-child", "--"]
