ARG BASE_OS_VERSION=24.04
FROM quay.io/openstack.trove/ubuntu:$BASE_OS_VERSION
LABEL maintainer="Trove Project (https://storyboard.openstack.org/#!/project/openstack/trove)"

ARG DATASTORE="mysql"
ARG DATASTORE_VERSION="5.7"
ARG APTOPTS="-y -qq --no-install-recommends --allow-unauthenticated"

RUN export DEBIAN_FRONTEND="noninteractive" \
    && export APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1

RUN apt-get update \
    && apt-get install $APTOPTS gnupg2 lsb-release apt-utils apt-transport-https ca-certificates software-properties-common curl \
    && apt-get -o Dpkg::Options::="--force-confmiss" install --reinstall netbase \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . /opt/trove/backup
WORKDIR /opt/trove/backup
RUN ./install.sh --datastore $DATASTORE --datastore-version $DATASTORE_VERSION

RUN apt-get update \
    && apt-get install $APTOPTS build-essential python3-setuptools python3-all python3-all-dev python3-pip libffi-dev libssl-dev libxml2-dev libxslt1-dev libyaml-dev libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 --no-cache-dir install -U -r requirements.txt --break-system-packages \
    && curl -sSL https://github.com/Yelp/dumb-init/releases/download/v1.2.2/dumb-init_1.2.2_amd64 -o /usr/local/bin/dumb-init \
    && chmod +x /usr/local/bin/dumb-init

ENTRYPOINT ["dumb-init", "--single-child", "--"]
