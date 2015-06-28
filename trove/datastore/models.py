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
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.openstack.common import log as logging


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
db_api = get_db_api()


def persisted_models():
    return {
        'datastore': DBDatastore,
        'capabilities': DBCapabilities,
        'datastore_version': DBDatastoreVersion,
        'capability_overrides': DBCapabilityOverrides,
    }


class DBDatastore(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'name', 'default_version_id']


class DBCapabilities(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'name', 'description', 'enabled']


class DBCapabilityOverrides(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'capability_id', 'datastore_version_id', 'enabled']


class DBDatastoreVersion(dbmodels.DatabaseModelBase):

    _data_fields = ['id', 'datastore_id', 'name', 'manager', 'image_id',
                    'packages', 'active']


class Capabilities(object):

    def __init__(self, datastore_version_id=None):
        self.capabilities = []
        self.datastore_version_id = datastore_version_id

    def __contains__(self, item):
        return item in [capability.name for capability in self.capabilities]

    def __len__(self):
        return len(self.capabilities)

    def __iter__(self):
        for item in self.capabilities:
            yield item

    def __repr__(self):
        return '<%s: %s>' % (type(self), self.capabilities)

    def add(self, capability, enabled):
        """
        Add a capability override to a datastore version.
        """
        if self.datastore_version_id is not None:
            DBCapabilityOverrides.create(
                capability_id=capability.id,
                datastore_version_id=self.datastore_version_id,
                enabled=enabled)
        self._load()

    def _load(self):
        """
        Bulk load and override default capabilities with configured
        datastore version specific settings.
        """
        capability_defaults = [Capability(c)
                               for c in DBCapabilities.find_all()]

        capability_overrides = []
        if self.datastore_version_id is not None:
            # This should always happen but if there is any future case where
            # we don't have a datastore version id number it won't stop
            # defaults from rendering.
            capability_overrides = [
                CapabilityOverride(ce)
                for ce in DBCapabilityOverrides.find_all(
                    datastore_version_id=self.datastore_version_id)
            ]

        def override(cap):
            # This logic is necessary to apply datastore version specific
            # capability overrides when they are present in the database.
            for capability_override in capability_overrides:
                if cap.id == capability_override.capability_id:
                    # we have a mapped entity that indicates this datastore
                    # version has an override so we honor that.
                    return capability_override

            # There were no overrides for this capability so we just hand it
            # right back.
            return cap

        self.capabilities = map(override, capability_defaults)

        LOG.debug('Capabilities for datastore %(ds_id)s: %(capabilities)s' %
                  {'ds_id': self.datastore_version_id,
                   'capabilities': self.capabilities})

    @classmethod
    def load(cls, datastore_version_id=None):
        """
        Generates a Capabilities object by looking up all capabilities from
        defaults and overrides and provides the one structure that should be
        used as the interface to controlling capabilities per datastore.

        :returns Capabilities:
        """
        self = cls(datastore_version_id)
        self._load()
        return self


class BaseCapability(object):
    def __init__(self, db_info):
        self.db_info = db_info

    def __repr__(self):
        return ('<%(my_class)s: name: %(name)s, enabled: %(enabled)s>' %
                {'my_class': type(self), 'name': self.name,
                 'enabled': self.enabled})

    @property
    def id(self):
        """
        The capability's id

        :returns str:
        """
        return self.db_info.id

    @property
    def enabled(self):
        """
        Is the capability/feature enabled?

        :returns bool:
        """
        return self.db_info.enabled

    def enable(self):
        """
        Enable the capability.
        """
        self.db_info.enabled = True
        self.db_info.save()

    def disable(self):
        """
        Disable the capability
        """
        self.db_info.enabled = False
        self.db_info.save()

    def delete(self):
        """
        Delete the capability from the database.
        """

        self.db_info.delete()


class CapabilityOverride(BaseCapability):
    """
    A capability override is simply an setting that applies to a
    specific datastore version that overrides the default setting in the
    base capability's entry for Trove.
    """
    def __init__(self, db_info):
        super(CapabilityOverride, self).__init__(db_info)
        # This *may* be better solved with a join in the SQLAlchemy model but
        # I was unable to get our query object to work properly for this.
        parent_capability = Capability.load(db_info.capability_id)
        if parent_capability:
            self.parent_name = parent_capability.name
            self.parent_description = parent_capability.description
        else:
            raise exception.CapabilityNotFound(
                _("Somehow we got a datastore version capability without a "
                  "parent, that shouldn't happen. %s") % db_info.capability_id)

    @property
    def name(self):
        """
        The name of the capability.

        :returns str:
        """
        return self.parent_name

    @property
    def description(self):
        """
        The description of the capability.

        :returns str:
        """
        return self.parent_description

    @property
    def capability_id(self):
        """
        Because capability overrides is an association table there are times
        where having the capability id is necessary.

        :returns str:
        """
        return self.db_info.capability_id

    @classmethod
    def load(cls, capability_id):
        """
        Generates a CapabilityOverride object from the capability_override id.

        :returns CapabilityOverride:
        """
        try:
            return cls(DBCapabilityOverrides.find_by(
                capability_id=capability_id))
        except exception.ModelNotFoundError:
            raise exception.CapabilityNotFound(
                _("Capability Override not found for "
                  "capability %s") % capability_id)

    @classmethod
    def create(cls, capability, datastore_version_id, enabled):
        """
        Create a new CapabilityOverride.

        :param capability:              The capability to be overridden for
                                        this DS Version
        :param datastore_version_id:    The datastore version to apply the
                                        override to.
        :param enabled:                 Set enabled to True or False

        :returns CapabilityOverride:
        """

        return CapabilityOverride(
            DBCapabilityOverrides.create(
                capability_id=capability.id,
                datastore_version_id=datastore_version_id,
                enabled=enabled)
        )


class Capability(BaseCapability):
    @property
    def name(self):
        """
        The Capability name

        :returns str:
        """
        return self.db_info.name

    @property
    def description(self):
        """
        The Capability description

        :returns str:
        """
        return self.db_info.description

    @classmethod
    def load(cls, capability_id_or_name):
        """
        Generates a Capability object by looking up the capability first by
        ID then by name.

        :returns Capability:
        """
        try:
            return cls(DBCapabilities.find_by(id=capability_id_or_name))
        except exception.ModelNotFoundError:
            try:
                return cls(DBCapabilities.find_by(name=capability_id_or_name))
            except exception.ModelNotFoundError:
                raise exception.CapabilityNotFound(
                    capability=capability_id_or_name)

    @classmethod
    def create(cls, name, description, enabled=False):
        """
        Creates a new capability.

        :returns Capability:
        """
        return Capability(DBCapabilities.create(
            name=name, description=description, enabled=enabled))


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
    def default_version_id(self):
        return self.db_info.default_version_id

    def delete(self):
        self.db_info.delete()


class Datastores(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls, only_active=True):
        datastores = DBDatastore.find_all()
        if only_active:
            datastores = datastores.join(DBDatastoreVersion).filter(
                DBDatastoreVersion.active == 1)
        return cls(datastores)

    def __iter__(self):
        for item in self.db_info:
            yield item


class DatastoreVersion(object):

    def __init__(self, db_info):
        self._capabilities = None
        self.db_info = db_info
        self._datastore_name = None

    @classmethod
    def load(cls, datastore, id_or_name):
        try:
            return cls(DBDatastoreVersion.find_by(datastore_id=datastore.id,
                                                  id=id_or_name))
        except exception.ModelNotFoundError:
            versions = DBDatastoreVersion.find_all(datastore_id=datastore.id,
                                                   name=id_or_name)
            if versions.count() == 0:
                raise exception.DatastoreVersionNotFound(version=id_or_name)
            if versions.count() > 1:
                raise exception.NoUniqueMatch(name=id_or_name)
            return cls(versions.first())

    @classmethod
    def load_by_uuid(cls, uuid):
        try:
            return cls(DBDatastoreVersion.find_by(id=uuid))
        except exception.ModelNotFoundError:
            raise exception.DatastoreVersionNotFound(version=uuid)

    @property
    def id(self):
        return self.db_info.id

    @property
    def datastore_id(self):
        return self.db_info.datastore_id

    @property
    def datastore_name(self):
        if self._datastore_name is None:
            self._datastore_name = Datastore.load(self.datastore_id).name
        return self._datastore_name

    # TODO(tim.simpson): This would be less confusing if it was called
    #                    "version" and datastore_name was called "name".
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
        return (True if self.db_info.active else False)

    @property
    def manager(self):
        return self.db_info.manager

    @property
    def capabilities(self):
        if self._capabilities is None:
            self._capabilities = Capabilities.load(self.db_info.id)

        return self._capabilities


class DatastoreVersions(object):

    def __init__(self, db_info):
        self.db_info = db_info

    @classmethod
    def load(cls, id_or_name, only_active=True):
        datastore = Datastore.load(id_or_name)
        if only_active:
            versions = DBDatastoreVersion.find_all(datastore_id=datastore.id,
                                                   active=True)
        else:
            versions = DBDatastoreVersion.find_all(datastore_id=datastore.id)
        return cls(versions)

    @classmethod
    def load_all(cls, only_active=True):
        if only_active:
            return cls(DBDatastoreVersion.find_all(active=True))
        return cls(DBDatastoreVersion.find_all())

    def __iter__(self):
        for item in self.db_info:
            yield item


def get_datastore_version(type=None, version=None, return_inactive=False):
    datastore = type or CONF.default_datastore
    if not datastore:
        raise exception.DatastoreDefaultDatastoreNotFound()
    datastore = Datastore.load(datastore)
    version = version or datastore.default_version_id
    if not version:
        raise exception.DatastoreDefaultVersionNotFound(
            datastore=datastore.name)
    datastore_version = DatastoreVersion.load(datastore, version)
    if datastore_version.datastore_id != datastore.id:
        raise exception.DatastoreNoVersion(datastore=datastore.name,
                                           version=datastore_version.name)
    if not datastore_version.active and not return_inactive:
        raise exception.DatastoreVersionInactive(
            version=datastore_version.name)
    return (datastore, datastore_version)


def update_datastore(name, default_version):
    db_api.configure_db(CONF)
    try:
        datastore = DBDatastore.find_by(name=name)
    except exception.ModelNotFoundError:
        # Create a new one
        datastore = DBDatastore()
        datastore.id = utils.generate_uuid()
        datastore.name = name

    if default_version:
        version = DatastoreVersion.load(datastore, default_version)
        if not version.active:
            raise exception.DatastoreVersionInactive(version=version.name)
        datastore.default_version_id = version.id
    else:
        datastore.default_version_id = None

    db_api.save(datastore)


def update_datastore_version(datastore, name, manager, image_id, packages,
                             active):
    db_api.configure_db(CONF)
    datastore = Datastore.load(datastore)
    try:
        version = DBDatastoreVersion.find_by(datastore_id=datastore.id,
                                             name=name)
    except exception.ModelNotFoundError:
        # Create a new one
        version = DBDatastoreVersion()
        version.id = utils.generate_uuid()
        version.name = name
        version.datastore_id = datastore.id
    version.manager = manager
    version.image_id = image_id
    version.packages = packages
    version.active = active
    db_api.save(version)
