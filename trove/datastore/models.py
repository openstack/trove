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

from oslo_log import log as logging
from oslo_utils import uuidutils

from trove.common import cfg
from trove.common.clients import create_nova_client
from trove.common import exception
from trove.common.i18n import _
from trove.common import timeutils
from trove.common import utils
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.flavor.models import Flavor as flavor_model
from trove.volume_type import models as volume_type_models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
db_api = get_db_api()


def persisted_models():
    return {
        'datastores': DBDatastore,
        'capabilities': DBCapabilities,
        'datastore_versions': DBDatastoreVersion,
        'capability_overrides': DBCapabilityOverrides,
        'datastore_version_metadata': DBDatastoreVersionMetadata
    }


class DBDatastore(dbmodels.DatabaseModelBase):

    _data_fields = ['name', 'default_version_id']
    _table_name = 'datastores'


class DBCapabilities(dbmodels.DatabaseModelBase):

    _data_fields = ['name', 'description', 'enabled']
    _table_name = 'capabilities'


class DBCapabilityOverrides(dbmodels.DatabaseModelBase):

    _data_fields = ['capability_id', 'datastore_version_id', 'enabled']
    _table_name = 'capability_overrides'


class DBDatastoreVersion(dbmodels.DatabaseModelBase):
    _data_fields = ['datastore_id', 'name', 'image_id', 'image_tags',
                    'packages', 'active', 'manager', 'version']
    _table_name = 'datastore_versions'


class DBDatastoreVersionMetadata(dbmodels.DatabaseModelBase):

    _data_fields = ['datastore_version_id', 'key', 'value',
                    'created', 'deleted', 'deleted_at', 'updated_at']
    _table_name = 'datastore_version_metadata'


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

        self.capabilities = [override(obj) for obj in capability_defaults]

        LOG.debug('Capabilities for datastore %(ds_id)s: %(capabilities)s',
                  {'ds_id': self.datastore_version_id,
                   'capabilities': self.capabilities})

    @classmethod
    def load(cls, datastore_version_id=None):
        """
        Generates a Capabilities object by looking up all capabilities from
        defaults and overrides and provides the one structure that should be
        used as the interface to controlling capabilities per datastore.

        :returns: Capabilities
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

        :returns: str
        """
        return self.db_info.id

    @property
    def enabled(self):
        """
        Is the capability/feature enabled?

        :returns: bool
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

        :returns: str
        """
        return self.parent_name

    @property
    def description(self):
        """
        The description of the capability.

        :returns: str
        """
        return self.parent_description

    @property
    def capability_id(self):
        """
        Because capability overrides is an association table there are times
        where having the capability id is necessary.

        :returns: str
        """
        return self.db_info.capability_id

    @classmethod
    def load(cls, capability_id):
        """
        Generates a CapabilityOverride object from the capability_override id.

        :returns: CapabilityOverride
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

        :returns: CapabilityOverride
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

        :returns: str
        """
        return self.db_info.name

    @property
    def description(self):
        """
        The Capability description

        :returns: str
        """
        return self.db_info.description

    @classmethod
    def load(cls, capability_id_or_name):
        """
        Generates a Capability object by looking up the capability first by
        ID then by name.

        :returns: Capability
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

        :returns: Capability
        """
        return Capability(DBCapabilities.create(
            name=name, description=description, enabled=enabled))


class Datastore(object):

    def __init__(self, db_info):
        self.db_info = db_info

    def __repr__(self, *args, **kwargs):
        return "%s(%s)" % (self.name, self.id)

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

    def __repr__(self, *args, **kwargs):
        return "%s(%s)" % (self.name, self.id)

    @classmethod
    def load(cls, datastore, id_or_name, version=None):
        if uuidutils.is_uuid_like(id_or_name):
            return cls(DBDatastoreVersion.find_by(datastore_id=datastore.id,
                                                  id=id_or_name))

        version = version or id_or_name
        versions = DBDatastoreVersion.find_all(datastore_id=datastore.id,
                                               name=id_or_name,
                                               version=version)
        if versions.count() == 0:
            raise exception.DatastoreVersionNotFound(version=version)
        if versions.count() > 1:
            raise exception.NoUniqueMatch(name=id_or_name)
        return cls(versions.first())

    @classmethod
    def load_by_uuid(cls, uuid):
        try:
            return cls(DBDatastoreVersion.find_by(id=uuid))
        except exception.ModelNotFoundError:
            raise exception.DatastoreVersionNotFound(version=uuid)

    def delete(self):
        self.db_info.delete()

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
    def image_tags(self):
        return self.db_info.image_tags

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
    def default(self):
        datastore = Datastore.load(self.datastore_id)
        return (datastore.default_version_id == self.db_info.id)

    @property
    def capabilities(self):
        if self._capabilities is None:
            self._capabilities = Capabilities.load(self.db_info.id)

        return self._capabilities

    @property
    def version(self):
        return self.db_info.version


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
        raise exception.DatastoreDefaultDatastoreNotDefined()
    try:
        datastore = Datastore.load(datastore)
    except exception.DatastoreNotFound:
        if not type:
            raise exception.DatastoreDefaultDatastoreNotFound(
                datastore=datastore)
        raise

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


def get_datastore_or_version(datastore=None, datastore_version=None):
    """
    Validate that the specified datastore/version exists, and return the
    corresponding ids.  This differs from 'get_datastore_version' in that
    you don't need to specify both - specifying only a datastore will
    return 'None' in the ds_ver field.  Raises DatastoreNoVersion if
    you pass in a ds_ver without a ds.  Originally designed for module
    management.

    :param datastore:           Datastore name or id
    :param datastore_version:   Version name or id
    :return:                    Tuple of ds_id, ds_ver_id if found
    """

    datastore_id = None
    datastore_version_id = None
    if datastore:
        if datastore_version:
            ds, ds_ver = get_datastore_version(
                type=datastore, version=datastore_version)
            datastore_id = ds.id
            datastore_version_id = ds_ver.id
        else:
            ds = Datastore.load(datastore)
            datastore_id = ds.id
    elif datastore_version:
        # Cannot specify version without datastore.
        raise exception.DatastoreNoVersion(
            datastore=datastore, version=datastore_version)
    return datastore_id, datastore_version_id


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


def update_datastore_version(datastore, name, manager, image_id, image_tags,
                             packages, active, version=None):
    """Create or update datastore version."""
    version = version or name
    db_api.configure_db(CONF)
    datastore = Datastore.load(datastore)
    try:
        ds_version = DBDatastoreVersion.find_by(datastore_id=datastore.id,
                                                name=name,
                                                version=version)
    except exception.ModelNotFoundError:
        # Create a new one
        ds_version = DBDatastoreVersion()
        ds_version.id = utils.generate_uuid()
        ds_version.name = name
        ds_version.version = version
        ds_version.datastore_id = datastore.id
    ds_version.manager = manager
    ds_version.image_id = image_id
    ds_version.image_tags = (",".join(image_tags)
                             if type(image_tags) is list else image_tags)
    ds_version.packages = packages
    ds_version.active = active

    db_api.save(ds_version)


class DatastoreVersionMetadata(object):
    @classmethod
    def _datastore_version_find(cls, datastore_name,
                                datastore_version_name):
        """
        Helper to find a datastore version id for a given
        datastore and datastore version name.
        """
        db_api.configure_db(CONF)
        db_ds_record = DBDatastore.find_by(
            name=datastore_name
        )
        db_dsv_record = DBDatastoreVersion.find_by(
            datastore_id=db_ds_record.id,
            name=datastore_version_name
        )

        return db_dsv_record.id

    @classmethod
    def _datastore_version_metadata_add(cls, datastore_name,
                                        datastore_version_name,
                                        datastore_version_id,
                                        key, value, exception_class):
        """
        Create a record of the specified key and value in the
        metadata table.
        """
        # if an association does not exist, create a new one.
        # if a deleted association exists, undelete it.
        # if an un-deleted association exists, raise an exception.

        try:
            db_record = DBDatastoreVersionMetadata.find_by(
                datastore_version_id=datastore_version_id,
                key=key, value=value)
            if db_record.deleted == 1:
                db_record.deleted = 0
                db_record.updated_at = timeutils.utcnow()
                db_record.save()
                return
            else:
                raise exception_class(
                    datastore=datastore_name,
                    datastore_version=datastore_version_name,
                    id=value)
        except exception.NotFound:
            pass

        # the record in the database only contains the datastore_verion_id
        DBDatastoreVersionMetadata.create(
            datastore_version_id=datastore_version_id,
            key=key, value=value)

    @classmethod
    def _datastore_version_metadata_delete(cls, datastore_name,
                                           datastore_version_name,
                                           key, value, exception_class):
        """
        Delete a record of the specified key and value in the
        metadata table.
        """
        # if an association does not exist, raise an exception
        # if a deleted association exists, raise an exception
        # if an un-deleted association exists, delete it

        datastore_version_id = cls._datastore_version_find(
            datastore_name,
            datastore_version_name)

        try:
            db_record = DBDatastoreVersionMetadata.find_by(
                datastore_version_id=datastore_version_id,
                key=key, value=value)
            if db_record.deleted == 0:
                db_record.delete()
                return
            else:
                raise exception_class(
                    datastore=datastore_name,
                    datastore_version=datastore_version_name,
                    id=value)
        except exception.ModelNotFoundError:
            raise exception_class(datastore=datastore_name,
                                  datastore_version=datastore_version_name,
                                  id=value)

    @classmethod
    def add_datastore_version_flavor_association(cls, datastore_name,
                                                 datastore_version_name,
                                                 flavor_ids):
        datastore_version_id = cls._datastore_version_find(
            datastore_name,
            datastore_version_name)

        for flavor_id in flavor_ids:
            cls._datastore_version_metadata_add(
                datastore_name, datastore_version_name,
                datastore_version_id, 'flavor', flavor_id,
                exception.DatastoreFlavorAssociationAlreadyExists)

    @classmethod
    def delete_datastore_version_flavor_association(cls, datastore_name,
                                                    datastore_version_name,
                                                    flavor_id):
        cls._datastore_version_metadata_delete(
            datastore_name, datastore_version_name, 'flavor', flavor_id,
            exception.DatastoreFlavorAssociationNotFound)

    @classmethod
    def list_datastore_version_flavor_associations(cls, context,
                                                   datastore_type,
                                                   datastore_version_id):
        if datastore_type and datastore_version_id:
            """
            All nova flavors are permitted for a datastore_version unless
            one or more entries are found in datastore_version_metadata,
            in which case only those are permitted.
            """
            (datastore, datastore_version) = get_datastore_version(
                type=datastore_type, version=datastore_version_id)
            # If datastore_version_id and flavor key exists in the
            # metadata table return all the associated flavors for
            # that datastore version.
            nova_flavors = create_nova_client(context).flavors.list()
            bound_flavors = DBDatastoreVersionMetadata.find_all(
                datastore_version_id=datastore_version.id,
                key='flavor', deleted=False
            )
            if (bound_flavors.count() != 0):
                bound_flavors = tuple(f.value for f in bound_flavors)
                # Generate a filtered list of nova flavors
                ds_nova_flavors = (f for f in nova_flavors
                                   if f.id in bound_flavors)
                associated_flavors = tuple(flavor_model(flavor=item)
                                           for item in ds_nova_flavors)
            else:
                # Return all nova flavors if no flavor metadata found
                # for datastore_version.
                associated_flavors = tuple(flavor_model(flavor=item)
                                           for item in nova_flavors)
            return associated_flavors
        else:
            msg = _("Specify both the datastore and datastore_version_id.")
            raise exception.BadRequest(msg)

    @classmethod
    def add_datastore_version_volume_type_association(cls, datastore_name,
                                                      datastore_version_name,
                                                      volume_type_names):
        datastore_version_id = cls._datastore_version_find(
            datastore_name,
            datastore_version_name)

        # the database record will contain
        # datastore_version_id, 'volume_type', volume_type_name
        for volume_type_name in volume_type_names:
            cls._datastore_version_metadata_add(
                datastore_name, datastore_version_name,
                datastore_version_id, 'volume_type', volume_type_name,
                exception.DatastoreVolumeTypeAssociationAlreadyExists)

    @classmethod
    def delete_datastore_version_volume_type_association(
            cls, datastore_name,
            datastore_version_name,
            volume_type_name):
        cls._datastore_version_metadata_delete(
            datastore_name, datastore_version_name, 'volume_type',
            volume_type_name,
            exception.DatastoreVolumeTypeAssociationNotFound)

    @classmethod
    def list_datastore_version_volume_type_associations(cls,
                                                        datastore_version_id):
        """
        List the datastore associations for a given datastore version id as
        found in datastore version metadata. Note that this may return an
        empty set (if no associations are provided)
        """
        if datastore_version_id:
            return DBDatastoreVersionMetadata.find_all(
                datastore_version_id=datastore_version_id,
                key='volume_type', deleted=False
            )
        else:
            msg = _("Specify the datastore_version_id.")
            raise exception.BadRequest(msg)

    @classmethod
    def list_datastore_volume_type_associations(cls,
                                                datastore_name,
                                                datastore_version_name):
        """
        List the datastore associations for a given datastore and version.
        """
        if datastore_name and datastore_version_name:
            datastore_version_id = cls._datastore_version_find(
                datastore_name, datastore_version_name)
            return cls.list_datastore_version_volume_type_associations(
                datastore_version_id)
        else:
            msg = _("Specify the datastore_name and datastore_version_name.")
            raise exception.BadRequest(msg)

    @classmethod
    def datastore_volume_type_associations_exist(cls,
                                                 datastore_name,
                                                 datastore_version_name):
        return cls.list_datastore_volume_type_associations(
            datastore_name,
            datastore_version_name).count() > 0

    @classmethod
    def allowed_datastore_version_volume_types(cls, context,
                                               datastore_name,
                                               datastore_version_name):
        """
        List all allowed volume types for a given datastore and
        datastore version. If datastore version metadata is
        provided, then the valid volume types in that list are
        allowed. If datastore version metadata is not provided
        then all volume types known to cinder are allowed.
        """
        if datastore_name and datastore_version_name:
            # first obtain the list in the dsvmetadata
            datastore_version_id = cls._datastore_version_find(
                datastore_name, datastore_version_name)

            metadata = cls.list_datastore_version_volume_type_associations(
                datastore_version_id)

            # then get the list of all volume types
            all_volume_types = volume_type_models.VolumeTypes(context)

            # if there's metadata: intersect,
            # else, whatever cinder has.
            if (metadata.count() != 0):
                # the volume types from metadata first
                ds_volume_types = tuple(f.value for f in metadata)

                # Cinder volume type names are unique, intersect
                allowed_volume_types = tuple(
                    f for f in all_volume_types
                    if ((f.name in ds_volume_types) or
                        (f.id in ds_volume_types)))
            else:
                allowed_volume_types = tuple(all_volume_types)

            return allowed_volume_types
        else:
            msg = _("Specify the datastore_name and datastore_version_name.")
            raise exception.BadRequest(msg)

    @classmethod
    def validate_volume_type(cls, context, volume_type,
                             datastore_name, datastore_version_name):
        if cls.datastore_volume_type_associations_exist(
                datastore_name, datastore_version_name):
            allowed = cls.allowed_datastore_version_volume_types(
                context, datastore_name, datastore_version_name)
            if len(allowed) == 0:
                raise exception.DatastoreVersionNoVolumeTypes(
                    datastore=datastore_name,
                    datastore_version=datastore_version_name)
            if volume_type is None:
                raise exception.DataStoreVersionVolumeTypeRequired(
                    datastore=datastore_name,
                    datastore_version=datastore_version_name)

            allowed_names = tuple(f.name for f in allowed)
            for n in allowed_names:
                LOG.debug("Volume Type: %s is allowed for datastore "
                          "%s, version %s." %
                          (n, datastore_name, datastore_version_name))
            if volume_type not in allowed_names:
                raise exception.DatastoreVolumeTypeAssociationNotFound(
                    datastore=datastore_name,
                    version_id=datastore_version_name,
                    id=volume_type)
