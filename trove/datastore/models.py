# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.db import models as dbmodels
from trove.db import get_db_api


CONF = cfg.CONF
db_api = get_db_api()


def persisted_models():
    return {
        'datastore': DBDatastore,
        'datastore_version': DBDatastoreVersion,
    }


class DBDatastore(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'name', 'manager', 'default_version_id']


class DBDatastoreVersion(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'datastore_id', 'name', 'image_id', 'packages',
                    'active']


class Datastore(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls, id_or_name):
        try:
            return cls(DBDatastore.find_by(id=id_or_name))
        except exception.ModelNotFoundError:
            try:
                return cls(DBDatastore.find_by(name=id_or_name))
            except exception.ModelNotFoundError:
                raise exception.DatastoreNotFound(datastore=id_or_name)

    @property
    def id(self):
        return self.db_info.id

    @property
    def name(self):
        return self.db_info.name

    @property
    def manager(self):
        return self.db_info.manager

    @property
    def default_version_id(self):
        return self.db_info.default_version_id


class Datastores(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls):
        return cls(DBDatastore.find_all())

    def __iter__(self):
        for item in self.db_info:
            yield item


class DatastoreVersion(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls, id_or_name):
        try:
            return cls(DBDatastoreVersion.find_by(id=id_or_name))
        except exception.ModelNotFoundError:
            try:
                return cls(DBDatastoreVersion.find_by(name=id_or_name))
            except exception.ModelNotFoundError:
                raise exception.DatastoreVersionNotFound(version=id_or_name)

    @property
    def id(self):
        return self.db_info.id

    @property
    def datastore_id(self):
        return self.db_info.datastore_id

    @property
    def name(self):
        return self.db_info.name

    @property
    def image_id(self):
        return self.db_info.image_id

    @property
    def packages(self):
        return self.db_info.packages

    @property
    def active(self):
        return self.db_info.active


class DatastoreVersions(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls, id_or_name, active=True):
        datastore = Datastore.load(id_or_name)
        return cls(DBDatastoreVersion.find_all(datastore_id=datastore.id,
                                               active=active))

    def __iter__(self):
        for item in self.db_info:
            yield item


def get_datastore_version(type=None, version=None):
    datastore = type or CONF.default_datastore
    if not datastore:
        raise exception.DatastoreDefaultDatastoreNotFound()
    datastore = Datastore.load(datastore)
    version = version or datastore.default_version_id
    if not version:
        raise exception.DatastoreDefaultVersionNotFound(datastore=
                                                        datastore.name)
    datastore_version = DatastoreVersion.load(version)
    if datastore_version.datastore_id != datastore.id:
        raise exception.DatastoreNoVersion(datastore=datastore.name,
                                           version=datastore_version.name)
    if not datastore_version.active:
        raise exception.DatastoreVersionInactive(version=
                                                 datastore_version.name)
    return (datastore, datastore_version)


def update_datastore(name, manager, default_version):
    db_api.configure_db(CONF)
    if default_version:
        version = DatastoreVersion.load(default_version)
        if not version.active:
            raise exception.DatastoreVersionInactive(version=
                                                     version.name)
    try:
        datastore = DBDatastore.find_by(name=name)
    except exception.ModelNotFoundError:
        # Create a new one
        datastore = DBDatastore()
        datastore.id = utils.generate_uuid()
        datastore.name = name
    datastore.manager = manager
    if default_version:
        datastore.default_version_id = version.id
    db_api.save(datastore)


def update_datastore_version(datastore, name, image_id, packages, active):
    db_api.configure_db(CONF)
    datastore = Datastore.load(datastore)
    try:
        version = DBDatastoreVersion.find_by(name=name)
    except exception.ModelNotFoundError:
        # Create a new one
        version = DBDatastoreVersion()
        version.id = utils.generate_uuid()
        version.name = name
    version.datastore_id = datastore.id
    version.image_id = image_id
    version.packages = packages
    version.active = active
    db_api.save(version)
