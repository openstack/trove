FROM ubuntu:18.04
LABEL maintainer="anlin.kong@gmail.com"

ARG DATASTORE="mysql"
ARG APTOPTS="-y -qq --no-install-recommends --allow-unauthenticated"
ARG PERCONA_XTRABACKUP_VERSION=24
ENV DEBIAN_FRONTEND noninteractive \
    APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1

RUN apt-get update \
    && apt-get install $APTOPTS gnupg2 lsb-release apt-utils apt-transport-https ca-certificates software-properties-common curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . /opt/trove/backup
WORKDIR /opt/trove/backup
RUN ./install.sh $DATASTORE ${PERCONA_XTRABACKUP_VERSION}

RUN apt-get update \
    && apt-get install $APTOPTS build-essential python3-setuptools python3-all python3-all-dev python3-pip libffi-dev libssl-dev libxml2-dev libxslt1-dev libyaml-dev \
    && apt-get clean \
    && pip3 --no-cache-dir install -U -r requirements.txt \
    && curl -sSL https://github.com/Yelp/dumb-init/releases/download/v1.2.2/dumb-init_1.2.2_amd64 -o /usr/local/bin/dumb-init \
    && chmod +x /usr/local/bin/dumb-init

ENTRYPOINT ["dumb-init", "--single-child", "--"]
