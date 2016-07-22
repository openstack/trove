#    Copyright 2010-2011 OpenStack Foundation
#    Copyright 2013-2014 Rackspace Hosting
#    All Rights Reserved.
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

"""Model classes that form the core of instances functionality."""
from datetime import datetime
from datetime import timedelta
import re

from novaclient import exceptions as nova_exceptions
from oslo_config.cfg import NoSuchOptError
from oslo_log import log as logging

from trove.backup.models import Backup
from trove.common import cfg
from trove.common import exception
from trove.common import i18n as i18n
import trove.common.instance as tr_instance
from trove.common.notification import StartNotification
from trove.common.remote import create_cinder_client
from trove.common.remote import create_dns_client
from trove.common.remote import create_guest_client
from trove.common.remote import create_nova_client
from trove.common import server_group as srv_grp
from trove.common import template
from trove.common import utils
from trove.configuration.models import Configuration
from trove.datastore import models as datastore_models
from trove.datastore.models import DBDatastoreVersionMetadata
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.extensions.security_group.models import SecurityGroup
from trove.instance.tasks import InstanceTask
from trove.instance.tasks import InstanceTasks
from trove.module import models as module_models
from trove.module import views as module_views
from trove.quota.quota import run_with_quotas
from trove.taskmanager import api as task_api

(_, _LE, _LI, _LW) = (i18n._, i18n._LE, i18n._LI, i18n._LW)

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def filter_ips(ips, white_list_regex, black_list_regex):
    """Return IPs matching white_list_regex and
       Filter out IPs matching black_list_regex.
    """
    return [ip for ip in ips if re.search(white_list_regex, ip)
            and not re.search(black_list_regex, ip)]


def load_server(context, instance_id, server_id):
    """
    Loads a server or raises an exception.
    :param context: request context used to access nova
    :param instance_id: the trove instance id corresponding to the nova server
    (informational only)
    :param server_id: the compute instance id which will be retrieved from nova
    :type context: trove.common.context.TroveContext
    :type instance_id: unicode
    :type server_id: unicode
    :rtype: novaclient.v2.servers.Server
    """
    client = create_nova_client(context)
    try:
        server = client.servers.get(server_id)
    except nova_exceptions.NotFound:
        LOG.error(_LE("Could not find nova server_id(%s)."), server_id)
        raise exception.ComputeInstanceNotFound(instance_id=instance_id,
                                                server_id=server_id)
    except nova_exceptions.ClientException as e:
        raise exception.TroveError(str(e))
    return server


class InstanceStatus(object):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    BUILD = "BUILD"
    FAILED = "FAILED"
    REBOOT = "REBOOT"
    RESIZE = "RESIZE"
    BACKUP = "BACKUP"
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    PROMOTE = "PROMOTE"
    EJECT = "EJECT"
    DETACH = "DETACH"


def validate_volume_size(size):
    if size is None:
        raise exception.VolumeSizeNotSpecified()
    max_size = CONF.max_accepted_volume_size
    if int(size) > max_size:
        msg = ("Volume 'size' cannot exceed maximum "
               "of %d GB, %s cannot be accepted."
               % (max_size, size))
        raise exception.VolumeQuotaExceeded(msg)


def load_simple_instance_server_status(context, db_info):
    """Loads a server or raises an exception."""
    if 'BUILDING' == db_info.task_status.action:
        db_info.server_status = "BUILD"
        db_info.addresses = {}
    else:
        client = create_nova_client(context)
        try:
            server = client.servers.get(db_info.compute_instance_id)
            db_info.server_status = server.status
            db_info.addresses = server.addresses
        except nova_exceptions.NotFound:
            db_info.server_status = "SHUTDOWN"
            db_info.addresses = {}


# Invalid states to contact the agent
AGENT_INVALID_STATUSES = ["BUILD", "REBOOT", "RESIZE", "PROMOTE", "EJECT"]


class SimpleInstance(object):
    """A simple view of an instance.
    This gets loaded directly from the local database, so its cheaper than
    creating the fully loaded Instance.  As the name implies this class knows
    nothing of the underlying Nova Compute Instance (i.e. server)
    -----------
    |         |
    |    i    |
    | t  n    |
    | r  s  ---------------------
    | o  t  |  datastore/guest  |
    | v  a  ---------------------
    | e  n    |
    |    c    |
    |    e    |
    |         |
    -----------
    """

    def __init__(self, context, db_info, datastore_status, root_password=None,
                 ds_version=None, ds=None, locality=None):
        """
        :type context: trove.common.context.TroveContext
        :type db_info: trove.instance.models.DBInstance
        :type datastore_status: trove.instance.models.InstanceServiceStatus
        :type root_password: str
        """
        self.context = context
        self.db_info = db_info
        self.datastore_status = datastore_status
        self.root_pass = root_password
        self._fault = None
        self._fault_loaded = False
        if ds_version is None:
            self.ds_version = (datastore_models.DatastoreVersion.
                               load_by_uuid(self.db_info.datastore_version_id))
        if ds is None:
            self.ds = (datastore_models.Datastore.
                       load(self.ds_version.datastore_id))
        self.locality = locality

        self.slave_list = None

    @property
    def addresses(self):
        # TODO(tim.simpson): This code attaches two parts of the Nova server to
        #                   db_info: "status" and "addresses". The idea
        #                   originally was to listen to events to update this
        #                   data and store it in the Trove database.
        #                   However, it may have been unwise as a year and a
        #                   half later we still have to load the server anyway
        #                   and this makes the code confusing.
        if hasattr(self.db_info, 'addresses'):
            return self.db_info.addresses
        else:
            return None

    @property
    def created(self):
        return self.db_info.created

    @property
    def dns_ip_address(self):
        """Returns the IP address to be used with DNS."""
        ips = self.get_visible_ip_addresses()
        if ips:
            return ips[0]

    @property
    def flavor_id(self):
        # Flavor ID is a str in the 1.0 API.
        return str(self.db_info.flavor_id)

    @property
    def hostname(self):
        return self.db_info.hostname

    def get_visible_ip_addresses(self):
        """Returns IPs that will be visible to the user."""
        if self.addresses is None:
            return None
        IPs = []
        for label in self.addresses:
            if (re.search(CONF.network_label_regex, label) and
                    len(self.addresses[label]) > 0):
                IPs.extend([addr.get('addr')
                            for addr in self.addresses[label]])
        # Includes ip addresses that match the regexp pattern
        if CONF.ip_regex and CONF.black_list_regex:
            IPs = filter_ips(IPs, CONF.ip_regex, CONF.black_list_regex)
        return IPs

    @property
    def id(self):
        return self.db_info.id

    @property
    def type(self):
        return self.db_info.type

    @property
    def tenant_id(self):
        return self.db_info.tenant_id

    @property
    def is_building(self):
        return self.status in [InstanceStatus.BUILD]

    @property
    def is_datastore_running(self):
        """True if the service status indicates datastore is up and running."""
        return self.datastore_status.status in MYSQL_RESPONSIVE_STATUSES

    def datastore_status_matches(self, service_status):
        return self.datastore_status.status == service_status

    @property
    def name(self):
        return self.db_info.name

    @property
    def server_id(self):
        return self.db_info.compute_instance_id

    @property
    def slave_of_id(self):
        return self.db_info.slave_of_id

    @property
    def datastore_status(self):
        """
        Returns the Service Status for this instance.  For example, the status
        of the mysql datastore which is running on the server...not the server
        status itself.
        :return: the current status of the datastore
        :rtype: trove.instance.models.InstanceServiceStatus
        """
        return self.__datastore_status

    @datastore_status.setter
    def datastore_status(self, datastore_status):
        if datastore_status and not isinstance(datastore_status,
                                               InstanceServiceStatus):
            raise ValueError("datastore_status must be of type "
                             "InstanceServiceStatus. Got %s instead." %
                             datastore_status.__class__.__name__)
        self.__datastore_status = datastore_status

    @property
    def status(self):
        # Check for taskmanager errors.
        if self.db_info.task_status.is_error:
            return InstanceStatus.ERROR

        # Check for taskmanager status.
        action = self.db_info.task_status.action
        if 'BUILDING' == action:
            if 'ERROR' == self.db_info.server_status:
                return InstanceStatus.ERROR
            return InstanceStatus.BUILD
        if 'REBOOTING' == action:
            return InstanceStatus.REBOOT
        if 'RESIZING' == action:
            return InstanceStatus.RESIZE
        if 'RESTART_REQUIRED' == action:
            return InstanceStatus.RESTART_REQUIRED
        if InstanceTasks.PROMOTING.action == action:
            return InstanceStatus.PROMOTE
        if InstanceTasks.EJECTING.action == action:
            return InstanceStatus.EJECT
        if InstanceTasks.LOGGING.action == action:
            return InstanceStatus.LOGGING
        if InstanceTasks.DETACHING.action == action:
            return InstanceStatus.DETACH

        # Check for server status.
        if self.db_info.server_status in ["BUILD", "ERROR", "REBOOT",
                                          "RESIZE"]:
            return self.db_info.server_status

        # As far as Trove is concerned, Nova instances in VERIFY_RESIZE should
        # still appear as though they are in RESIZE.
        if self.db_info.server_status in ["VERIFY_RESIZE"]:
            return InstanceStatus.RESIZE

        # Check if there is a backup running for this instance
        if Backup.running(self.id):
            return InstanceStatus.BACKUP

        # Report as Shutdown while deleting, unless there's an error.
        if 'DELETING' == action:
            if self.db_info.server_status in ["ACTIVE", "SHUTDOWN", "DELETED"]:
                return InstanceStatus.SHUTDOWN
            else:
                LOG.error(_LE("While shutting down instance (%(instance)s): "
                              "server had status (%(status)s)."),
                          {'instance': self.id,
                           'status': self.db_info.server_status})
                return InstanceStatus.ERROR

        # Check against the service status.
        # The service is only paused during a reboot.
        if tr_instance.ServiceStatuses.PAUSED == self.datastore_status.status:
            return InstanceStatus.REBOOT
        # If the service status is NEW, then we are building.
        if tr_instance.ServiceStatuses.NEW == self.datastore_status.status:
            return InstanceStatus.BUILD

        # For everything else we can look at the service status mapping.
        return self.datastore_status.status.api_status

    @property
    def updated(self):
        return self.db_info.updated

    @property
    def volume_id(self):
        return self.db_info.volume_id

    @property
    def volume_size(self):
        return self.db_info.volume_size

    @property
    def datastore_version(self):
        return self.ds_version

    @property
    def datastore(self):
        return self.ds

    @property
    def volume_support(self):
        return CONF.get(self.datastore_version.manager).volume_support

    @property
    def device_path(self):
        return CONF.get(self.datastore_version.manager).device_path

    @property
    def root_password(self):
        return self.root_pass

    @property
    def fault(self):
        # Fault can be non-existent, so we have a loaded flag
        if not self._fault_loaded:
            try:
                self._fault = DBInstanceFault.find_by(instance_id=self.id)
                # Get rid of the stack trace if we're not admin
                if not self.context.is_admin:
                    self._fault.details = None
            except exception.ModelNotFoundError:
                pass
            self._fault_loaded = True
        return self._fault

    @property
    def configuration(self):
        if self.db_info.configuration_id is not None:
            return Configuration.load(self.context,
                                      self.db_info.configuration_id)

    @property
    def slaves(self):
        if self.slave_list is None:
            self.slave_list = DBInstance.find_all(tenant_id=self.tenant_id,
                                                  slave_of_id=self.id,
                                                  deleted=False).all()
        return self.slave_list

    @property
    def cluster_id(self):
        return self.db_info.cluster_id

    @property
    def shard_id(self):
        return self.db_info.shard_id


class DetailInstance(SimpleInstance):
    """A detailed view of an Instance.

    This loads a SimpleInstance and then adds additional data for the
    instance from the guest.
    """

    def __init__(self, context, db_info, datastore_status):
        super(DetailInstance, self).__init__(context, db_info,
                                             datastore_status)
        self._volume_used = None
        self._volume_total = None

    @property
    def volume_used(self):
        return self._volume_used

    @volume_used.setter
    def volume_used(self, value):
        self._volume_used = value

    @property
    def volume_total(self):
        return self._volume_total

    @volume_total.setter
    def volume_total(self, value):
        self._volume_total = value


def get_db_info(context, id, cluster_id=None, include_deleted=False):
    """
    Retrieves an instance of the managed datastore from the persisted
    storage based on the ID and Context
    :param context: the context which owns the instance
    :type context: trove.common.context.TroveContext
    :param id: the unique ID of the instance
    :type id: unicode or str
    :param cluster_id: the unique ID of the cluster
    :type cluster_id: unicode or str
    :return: a record of the instance as its state exists in persisted storage
    :rtype: trove.instance.models.DBInstance
    """
    if context is None:
        raise TypeError("Argument context not defined.")
    elif id is None:
        raise TypeError("Argument id not defined.")

    args = {'id': id}
    if cluster_id is not None:
        args['cluster_id'] = cluster_id
    if not include_deleted:
        args['deleted'] = False
    try:
        db_info = DBInstance.find_by(context=context, **args)
    except exception.NotFound:
        raise exception.NotFound(uuid=id)
    return db_info


def load_any_instance(context, id, load_server=True):
    # Try to load an instance with a server.
    # If that fails, try to load it without the server.
    try:
        return load_instance(BuiltInstance, context, id,
                             needs_server=load_server)
    except exception.UnprocessableEntity:
        LOG.warning(_LW("Could not load instance %s."), id)
        return load_instance(FreshInstance, context, id, needs_server=False)


def load_instance(cls, context, id, needs_server=False,
                  include_deleted=False):
    db_info = get_db_info(context, id, include_deleted=include_deleted)
    if not needs_server:
        # TODO(tim.simpson): When we have notifications this won't be
        # necessary and instead we'll just use the server_status field from
        # the instance table.
        load_simple_instance_server_status(context, db_info)
        server = None
    else:
        try:
            server = load_server(context, db_info.id,
                                 db_info.compute_instance_id)
            # TODO(tim.simpson): Remove this hack when we have notifications!
            db_info.server_status = server.status
            db_info.addresses = server.addresses
        except exception.ComputeInstanceNotFound:
            LOG.error(_LE("Could not load compute instance %s."),
                      db_info.compute_instance_id)
            raise exception.UnprocessableEntity("Instance %s is not ready." %
                                                id)

    service_status = InstanceServiceStatus.find_by(instance_id=id)
    LOG.debug("Instance %(instance_id)s service status is %(service_status)s.",
              {'instance_id': id, 'service_status': service_status.status})
    return cls(context, db_info, server, service_status)


def load_instance_with_info(cls, context, id, cluster_id=None):
    db_info = get_db_info(context, id, cluster_id)
    load_simple_instance_server_status(context, db_info)
    service_status = InstanceServiceStatus.find_by(instance_id=id)
    LOG.debug("Instance %(instance_id)s service status is %(service_status)s.",
              {'instance_id': id, 'service_status': service_status.status})
    instance = cls(context, db_info, service_status)
    load_guest_info(instance, context, id)
    load_server_group_info(instance, context, db_info.compute_instance_id)
    return instance


def load_guest_info(instance, context, id):
    if instance.status not in AGENT_INVALID_STATUSES:
        guest = create_guest_client(context, id)
        try:
            volume_info = guest.get_volume_info()
            instance.volume_used = volume_info['used']
            instance.volume_total = volume_info['total']
        except Exception as e:
            LOG.error(e)
    return instance


def load_server_group_info(instance, context, compute_id):
    server_group = srv_grp.ServerGroup.load(context, compute_id)
    if server_group:
        instance.locality = srv_grp.ServerGroup.get_locality(server_group)


class BaseInstance(SimpleInstance):
    """Represents an instance.
    -----------
    |         |
    |    i  ---------------------
    | t  n  |  compute instance |
    | r  s  ---------------------
    | o  t    |
    | v  a    |
    | e  n  ---------------------
    |    c  |  datastore/guest  |
    |    e  ---------------------
    |         |
    -----------
    """

    def __init__(self, context, db_info, server, datastore_status):
        """
        Creates a new initialized representation of an instance composed of its
        state in the database and its state from Nova

        :param context: the request context which contains the tenant that owns
        this instance
        :param db_info: the current state of this instance as it exists in the
        db
        :param server: the current state of this instance as it exists in the
        Nova
        :param datastore_status: the current state of the datastore on this
        instance at it exists in the db
        :type context: trove.common.context.TroveContext
        :type db_info: trove.instance.models.DBInstance
        :type server: novaclient.v2.servers.Server
        :typdatastore_statusus: trove.instance.models.InstanceServiceStatus
        """
        super(BaseInstance, self).__init__(context, db_info, datastore_status)
        self.server = server
        self._guest = None
        self._nova_client = None
        self._volume_client = None
        self._server_group = None
        self._server_group_loaded = False

    def get_guest(self):
        return create_guest_client(self.context, self.db_info.id)

    def delete(self):
        def _delete_resources():
            if self.is_building:
                raise exception.UnprocessableEntity("Instance %s is not ready."
                                                    % self.id)
            LOG.debug("Deleting instance with compute id = %s.",
                      self.db_info.compute_instance_id)

            from trove.cluster.models import is_cluster_deleting
            if (self.db_info.cluster_id is not None and not
               is_cluster_deleting(self.context, self.db_info.cluster_id)):
                raise exception.ClusterInstanceOperationNotSupported()

            if self.slaves:
                msg = _("Detach replicas before deleting replica source.")
                LOG.warning(msg)
                raise exception.ReplicaSourceDeleteForbidden(msg)

            self.update_db(task_status=InstanceTasks.DELETING,
                           configuration_id=None)
            task_api.API(self.context).delete_instance(self.id)

        deltas = {'instances': -1}
        if self.volume_support:
            deltas['volumes'] = -self.volume_size
        return run_with_quotas(self.tenant_id,
                               deltas,
                               _delete_resources)

    def _delete_resources(self, deleted_at):
        """Implemented in subclass."""
        pass

    def delete_async(self):
        deleted_at = datetime.utcnow()
        self._delete_resources(deleted_at)
        LOG.debug("Setting instance %s to be deleted.", self.id)
        self.update_db(deleted=True, deleted_at=deleted_at,
                       task_status=InstanceTasks.NONE)
        self.set_servicestatus_deleted()
        self.set_instance_fault_deleted()
        # Delete associated security group
        if CONF.trove_security_groups_support:
            SecurityGroup.delete_for_instance(self.db_info.id,
                                              self.context)

    @property
    def guest(self):
        if not self._guest:
            self._guest = self.get_guest()
        return self._guest

    @property
    def nova_client(self):
        if not self._nova_client:
            self._nova_client = create_nova_client(self.context)
        return self._nova_client

    def update_db(self, **values):
        self.db_info = DBInstance.find_by(id=self.id, deleted=False)
        for key in values:
            setattr(self.db_info, key, values[key])
        self.db_info.save()

    def set_servicestatus_deleted(self):
        del_instance = InstanceServiceStatus.find_by(instance_id=self.id)
        del_instance.set_status(tr_instance.ServiceStatuses.DELETED)
        del_instance.save()

    def set_instance_fault_deleted(self):
        try:
            del_fault = DBInstanceFault.find_by(instance_id=self.id)
            del_fault.deleted = True
            del_fault.deleted_at = datetime.utcnow()
            del_fault.save()
        except exception.ModelNotFoundError:
            pass

    @property
    def volume_client(self):
        if not self._volume_client:
            self._volume_client = create_cinder_client(self.context)
        return self._volume_client

    def reset_task_status(self):
        LOG.info(_LI("Resetting task status to NONE on instance %s."),
                 self.id)
        self.update_db(task_status=InstanceTasks.NONE)

    @property
    def server_group(self):
        # The server group could be empty, so we need a flag to cache it
        if not self._server_group_loaded:
            self._server_group = srv_grp.ServerGroup.load(
                self.context, self.db_info.compute_instance_id)
            self._server_group_loaded = True
        return self._server_group


class FreshInstance(BaseInstance):
    @classmethod
    def load(cls, context, id):
        return load_instance(cls, context, id, needs_server=False)


class BuiltInstance(BaseInstance):
    @classmethod
    def load(cls, context, id):
        return load_instance(cls, context, id, needs_server=True)


class Instance(BuiltInstance):
    """Represents an instance.

    The life span of this object should be limited. Do not store them or
    pass them between threads.

    """

    @classmethod
    def get_root_on_create(cls, datastore_manager):
        try:
            root_on_create = CONF.get(datastore_manager).root_on_create
            return root_on_create
        except NoSuchOptError:
            LOG.debug("root_on_create not configured for %s,"
                      " hence defaulting the value to False.",
                      datastore_manager)
            return False

    @classmethod
    def create(cls, context, name, flavor_id, image_id, databases, users,
               datastore, datastore_version, volume_size, backup_id,
               availability_zone=None, nics=None,
               configuration_id=None, slave_of_id=None, cluster_config=None,
               replica_count=None, volume_type=None, modules=None,
               locality=None):

        call_args = {
            'name': name,
            'flavor_id': flavor_id,
            'datastore': datastore.name if datastore else None,
            'datastore_version': datastore_version.name,
            'image_id': image_id,
            'availability_zone': availability_zone,
        }

        # All nova flavors are permitted for a datastore-version unless one
        # or more entries are found in datastore_version_metadata,
        # in which case only those are permitted.
        bound_flavors = DBDatastoreVersionMetadata.find_all(
            datastore_version_id=datastore_version.id,
            key='flavor', deleted=False
        )
        if bound_flavors.count() > 0:
            valid_flavors = tuple(f.value for f in bound_flavors)
            if flavor_id not in valid_flavors:
                raise exception.DatastoreFlavorAssociationNotFound(
                    datastore=datastore.name,
                    datastore_version=datastore_version.name,
                    flavor_id=flavor_id)

        datastore_cfg = CONF.get(datastore_version.manager)
        client = create_nova_client(context)
        try:
            flavor = client.flavors.get(flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=flavor_id)

        deltas = {'instances': 1}
        volume_support = datastore_cfg.volume_support
        if volume_support:
            call_args['volume_size'] = volume_size
            validate_volume_size(volume_size)
            deltas['volumes'] = volume_size
            # Instance volume should have enough space for the backup
            # Backup, and volume sizes are in GBs
            target_size = volume_size
        else:
            target_size = flavor.disk  # local_storage
            if volume_size is not None:
                raise exception.VolumeNotSupported()
            if datastore_cfg.device_path:
                if flavor.ephemeral == 0:
                    raise exception.LocalStorageNotSpecified(flavor=flavor_id)
                target_size = flavor.ephemeral  # ephemeral_Storage

        if backup_id:
            call_args['backup_id'] = backup_id
            backup_info = Backup.get_by_id(context, backup_id)
            if not backup_info.is_done_successfuly:
                raise exception.BackupNotCompleteError(
                    backup_id=backup_id, state=backup_info.state)

            if backup_info.size > target_size:
                raise exception.BackupTooLarge(
                    backup_size=backup_info.size, disk_size=target_size)

            if not backup_info.check_swift_object_exist(
                    context,
                    verify_checksum=CONF.verify_swift_checksum_on_restore):
                raise exception.BackupFileNotFound(
                    location=backup_info.location)

            if (backup_info.datastore_version_id
                    and backup_info.datastore.name != datastore.name):
                raise exception.BackupDatastoreMismatchError(
                    datastore1=backup_info.datastore.name,
                    datastore2=datastore.name)

        if slave_of_id:
            call_args['replica_of'] = slave_of_id
            call_args['replica_count'] = replica_count
            replication_support = datastore_cfg.replication_strategy
            if not replication_support:
                raise exception.ReplicationNotSupported(
                    datastore=datastore.name)
            try:
                # looking for replica source
                replica_source = DBInstance.find_by(
                    context,
                    id=slave_of_id,
                    deleted=False)
                if replica_source.slave_of_id:
                    raise exception.Forbidden(
                        _("Cannot create a replica of a replica %(id)s.")
                        % {'id': slave_of_id})
                # load the replica source status to check if
                # source is available
                load_simple_instance_server_status(
                    context,
                    replica_source)
                replica_source_instance = Instance(
                    context, replica_source,
                    None,
                    InstanceServiceStatus.find_by(
                        context,
                        instance_id=slave_of_id))
                replica_source_instance.validate_can_perform_action()
            except exception.ModelNotFoundError:
                LOG.exception(
                    _("Cannot create a replica of %(id)s "
                      "as that instance could not be found.")
                    % {'id': slave_of_id})
                raise exception.NotFound(uuid=slave_of_id)
        elif replica_count and replica_count != 1:
            raise exception.Forbidden(_(
                "Replica count only valid when creating replicas. Cannot "
                "create %(count)d instances.") % {'count': replica_count})
        multi_replica = slave_of_id and replica_count and replica_count > 1
        instance_count = replica_count if multi_replica else 1
        if locality:
            call_args['locality'] = locality

        if not nics:
            nics = []
        if CONF.default_neutron_networks:
            nics = [{"net-id": net_id}
                    for net_id in CONF.default_neutron_networks] + nics
        if nics:
            call_args['nics'] = nics
        if cluster_config:
            call_args['cluster_id'] = cluster_config.get("id", None)

        if not modules:
            modules = []
        module_ids = [mod['id'] for mod in modules]
        modules = module_models.Modules.load_by_ids(context, module_ids)
        auto_apply_modules = module_models.Modules.load_auto_apply(
            context, datastore.id, datastore_version.id)
        for aa_module in auto_apply_modules:
            if aa_module.id not in module_ids:
                modules.append(aa_module)
        module_list = []
        for module in modules:
            module.contents = module_models.Module.deprocess_contents(
                module.contents)
            module_info = module_views.DetailedModuleView(module).data(
                include_contents=True)
            module_list.append(module_info)

        def _create_resources():

            if cluster_config:
                cluster_id = cluster_config.get("id", None)
                shard_id = cluster_config.get("shard_id", None)
                instance_type = cluster_config.get("instance_type", None)
            else:
                cluster_id = shard_id = instance_type = None

            ids = []
            names = []
            root_passwords = []
            root_password = None
            for instance_index in range(0, instance_count):
                db_info = DBInstance.create(
                    name=name, flavor_id=flavor_id, tenant_id=context.tenant,
                    volume_size=volume_size,
                    datastore_version_id=datastore_version.id,
                    task_status=InstanceTasks.BUILDING,
                    configuration_id=configuration_id,
                    slave_of_id=slave_of_id, cluster_id=cluster_id,
                    shard_id=shard_id, type=instance_type)
                LOG.debug("Tenant %(tenant)s created new Trove instance "
                          "%(db)s.",
                          {'tenant': context.tenant, 'db': db_info.id})

                instance_id = db_info.id
                cls.add_instance_modules(context, instance_id, modules)
                instance_name = name
                ids.append(instance_id)
                names.append(instance_name)
                root_passwords.append(None)
                # change the name to be name + replica_number if more than one
                if multi_replica:
                    replica_number = instance_index + 1
                    names[instance_index] += '-' + str(replica_number)
                    setattr(db_info, 'name', names[instance_index])
                    db_info.save()

                # if a configuration group is associated with an instance,
                # generate an overrides dict to pass into the instance creation
                # method

                config = Configuration(context, configuration_id)
                overrides = config.get_configuration_overrides()
                service_status = InstanceServiceStatus.create(
                    instance_id=instance_id,
                    status=tr_instance.ServiceStatuses.NEW)

                if CONF.trove_dns_support:
                    dns_client = create_dns_client(context)
                    hostname = dns_client.determine_hostname(instance_id)
                    db_info.hostname = hostname
                    db_info.save()

                if cls.get_root_on_create(
                        datastore_version.manager) and not backup_id:
                    root_password = utils.generate_random_password()
                    root_passwords[instance_index] = root_password

            if instance_count > 1:
                instance_id = ids
                instance_name = names
                root_password = root_passwords
            task_api.API(context).create_instance(
                instance_id, instance_name, flavor, image_id, databases, users,
                datastore_version.manager, datastore_version.packages,
                volume_size, backup_id, availability_zone, root_password,
                nics, overrides, slave_of_id, cluster_config,
                volume_type=volume_type, modules=module_list,
                locality=locality)

            return SimpleInstance(context, db_info, service_status,
                                  root_password, locality=locality)

        with StartNotification(context, **call_args):
            return run_with_quotas(context.tenant, deltas, _create_resources)

    @classmethod
    def add_instance_modules(cls, context, instance_id, modules):
        for module in modules:
            module_models.InstanceModule.create(
                context, instance_id, module.id, module.md5)

    def get_flavor(self):
        client = create_nova_client(self.context)
        return client.flavors.get(self.flavor_id)

    def get_default_configuration_template(self):
        flavor = self.get_flavor()
        LOG.debug("Getting default config template for datastore version "
                  "%(ds_version)s and flavor %(flavor)s.",
                  {'ds_version': self.ds_version, 'flavor': flavor})
        config = template.SingleInstanceConfigTemplate(
            self.ds_version, flavor, self.id)
        return config.render_dict()

    def resize_flavor(self, new_flavor_id):
        self.validate_can_perform_action()
        LOG.info(_LI("Resizing instance %(instance_id)s flavor to "
                     "%(flavor_id)s."),
                 {'instance_id': self.id, 'flavor_id': new_flavor_id})
        if self.db_info.cluster_id is not None:
            raise exception.ClusterInstanceOperationNotSupported()

        # Validate that the old and new flavor IDs are not the same, new flavor
        # can be found and has ephemeral/volume support if required by the
        # current flavor.
        if self.flavor_id == new_flavor_id:
            raise exception.BadRequest(_("The new flavor id must be different "
                                         "than the current flavor id of '%s'.")
                                       % self.flavor_id)
        client = create_nova_client(self.context)
        try:
            new_flavor = client.flavors.get(new_flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=new_flavor_id)

        old_flavor = client.flavors.get(self.flavor_id)
        if self.volume_support:
            if new_flavor.ephemeral != 0:
                raise exception.LocalStorageNotSupported()
        elif self.device_path is not None:
            # ephemeral support enabled
            if new_flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=new_flavor_id)

        # Set the task to RESIZING and begin the async call before returning.
        self.update_db(task_status=InstanceTasks.RESIZING)
        LOG.debug("Instance %s set to RESIZING.", self.id)
        task_api.API(self.context).resize_flavor(self.id, old_flavor,
                                                 new_flavor)

    def resize_volume(self, new_size):
        def _resize_resources():
            self.validate_can_perform_action()
            LOG.info(_LI("Resizing volume of instance %s."), self.id)
            if self.db_info.cluster_id is not None:
                raise exception.ClusterInstanceOperationNotSupported()
            old_size = self.volume_size
            if int(new_size) <= old_size:
                raise exception.BadRequest(_("The new volume 'size' must be "
                                             "larger than the current volume "
                                             "size of '%s'.") % old_size)
            # Set the task to Resizing before sending off to the taskmanager
            self.update_db(task_status=InstanceTasks.RESIZING)
            task_api.API(self.context).resize_volume(new_size, self.id)

        if not self.volume_size:
            raise exception.BadRequest(_("Instance %s has no volume.")
                                       % self.id)
        new_size_l = int(new_size)
        validate_volume_size(new_size_l)
        return run_with_quotas(self.tenant_id,
                               {'volumes': new_size_l - self.volume_size},
                               _resize_resources)

    def reboot(self):
        self.validate_can_perform_action()
        LOG.info(_LI("Rebooting instance %s."), self.id)
        if self.db_info.cluster_id is not None and not self.context.is_admin:
            raise exception.ClusterInstanceOperationNotSupported()
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).reboot(self.id)

    def restart(self):
        self.validate_can_perform_action()
        LOG.info(_LI("Restarting datastore on instance %s."), self.id)
        if self.db_info.cluster_id is not None and not self.context.is_admin:
            raise exception.ClusterInstanceOperationNotSupported()
        # Set our local status since Nova might not change it quick enough.
        # TODO(tim.simpson): Possible bad stuff can happen if this service
        #                   shuts down before it can set status to NONE.
        #                   We need a last updated time to mitigate this;
        #                   after some period of tolerance, we'll assume the
        #                   status is no longer in effect.
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).restart(self.id)

    def detach_replica(self):
        self.validate_can_perform_action()
        LOG.info(_LI("Detaching instance %s from its replication source."),
                 self.id)
        if not self.slave_of_id:
            raise exception.BadRequest(_("Instance %s is not a replica.")
                                       % self.id)

        self.update_db(task_status=InstanceTasks.DETACHING)

        task_api.API(self.context).detach_replica(self.id)

    def promote_to_replica_source(self):
        self.validate_can_perform_action()
        LOG.info(_LI("Promoting instance %s to replication source."), self.id)
        if not self.slave_of_id:
            raise exception.BadRequest(_("Instance %s is not a replica.")
                                       % self.id)

        # Update task status of master and all slaves
        master = BuiltInstance.load(self.context, self.slave_of_id)
        for dbinfo in [master.db_info] + master.slaves:
            setattr(dbinfo, 'task_status', InstanceTasks.PROMOTING)
            dbinfo.save()

        task_api.API(self.context).promote_to_replica_source(self.id)

    def eject_replica_source(self):
        self.validate_can_perform_action()
        LOG.info(_LI("Ejecting replica source %s from its replication set."),
                 self.id)

        if not self.slaves:
            raise exception.BadRequest(_("Instance %s is not a replica"
                                       " source.") % self.id)
        service = InstanceServiceStatus.find_by(instance_id=self.id)
        last_heartbeat_delta = datetime.utcnow() - service.updated_at
        agent_expiry_interval = timedelta(seconds=CONF.agent_heartbeat_expiry)
        if last_heartbeat_delta < agent_expiry_interval:
            raise exception.BadRequest(_("Replica Source %s cannot be ejected"
                                         " as it has a current heartbeat")
                                       % self.id)

        # Update task status of master and all slaves
        for dbinfo in [self.db_info] + self.slaves:
            setattr(dbinfo, 'task_status', InstanceTasks.EJECTING)
            dbinfo.save()

        task_api.API(self.context).eject_replica_source(self.id)

    def migrate(self, host=None):
        self.validate_can_perform_action()
        LOG.info(_LI("Migrating instance id = %(instance_id)s "
                     "to host = %(host)s."),
                 {'instance_id': self.id, 'host': host})
        self.update_db(task_status=InstanceTasks.MIGRATING)
        task_api.API(self.context).migrate(self.id, host)

    def validate_can_perform_action(self):
        """
        Raises exception if an instance action cannot currently be performed.
        """
        # cases where action cannot be performed
        if self.db_info.server_status != 'ACTIVE':
            status = self.db_info.server_status
        elif (self.db_info.task_status != InstanceTasks.NONE and
              self.db_info.task_status != InstanceTasks.RESTART_REQUIRED):
            status = self.db_info.task_status
        elif not self.datastore_status.status.action_is_allowed:
            status = self.status
        elif Backup.running(self.id):
            status = InstanceStatus.BACKUP
        else:
            # action can be performed
            return

        msg = (_("Instance %(instance_id)s is not currently available for an "
                 "action to be performed (status was %(action_status)s).") %
               {'instance_id': self.id, 'action_status': status})
        LOG.error(msg)
        raise exception.UnprocessableEntity(msg)

    def _validate_can_perform_assign(self):
        """
        Raises exception if a configuration assign cannot
        currently be performed
        """
        # check if the instance already has a configuration assigned
        if self.db_info.configuration_id:
            raise exception.ConfigurationAlreadyAttached(
                instance_id=self.id,
                configuration_id=self.db_info.configuration_id)

        # check if the instance is not ACTIVE or has tasks
        status = None
        if self.db_info.server_status != InstanceStatus.ACTIVE:
            status = self.db_info.server_status
        elif self.db_info.task_status != InstanceTasks.NONE:
            status = self.db_info.task_status.action

        if status:
            raise exception.InvalidInstanceState(instance_id=self.id,
                                                 status=status)

    def unassign_configuration(self):
        LOG.debug("Unassigning the configuration from the instance %s.",
                  self.id)
        if self.configuration and self.configuration.id:
            LOG.debug("Unassigning the configuration id %s.",
                      self.configuration.id)

            self.guest.update_overrides({}, remove=True)

            # Dynamically reset the configuration values back to their default
            # values from the configuration template.
            # Reset the values only if the default is available for all of
            # them and restart is not required by any.
            # Mark the instance with a 'RESTART_REQUIRED' status otherwise.
            flavor = self.get_flavor()
            default_config = self._render_config_dict(flavor)
            current_config = Configuration(self.context, self.configuration.id)
            current_overrides = current_config.get_configuration_overrides()
            # Check the configuration template has defaults for all modified
            # values.
            has_defaults_for_all = all(key in default_config.keys()
                                       for key in current_overrides.keys())
            if (not current_config.does_configuration_need_restart() and
                    has_defaults_for_all):
                self.guest.apply_overrides(
                    {k: v for k, v in default_config.items()
                     if k in current_overrides})
            else:
                LOG.debug(
                    "Could not revert all configuration changes dynamically. "
                    "A restart will be required.")
                self.update_db(task_status=InstanceTasks.RESTART_REQUIRED)
        else:
            LOG.debug("No configuration found on instance. Skipping.")

    def assign_configuration(self, configuration_id):
        self._validate_can_perform_assign()

        try:
            configuration = Configuration.load(self.context, configuration_id)
        except exception.ModelNotFoundError:
            raise exception.NotFound(
                message='Configuration group id: %s could not be found.'
                % configuration_id)

        config_ds_v = configuration.datastore_version_id
        inst_ds_v = self.db_info.datastore_version_id
        if (config_ds_v != inst_ds_v):
            raise exception.ConfigurationDatastoreNotMatchInstance(
                config_datastore_version=config_ds_v,
                instance_datastore_version=inst_ds_v)

        config = Configuration(self.context, configuration.id)
        LOG.debug("Config is %s.", config)

        self.update_overrides(config)
        self.update_db(configuration_id=configuration.id)

    def update_overrides(self, config):
        LOG.debug("Updating or removing overrides for instance %s.", self.id)

        overrides = config.get_configuration_overrides()
        self.guest.update_overrides(overrides)

        # Apply the new configuration values dynamically to the running
        # datastore service.
        # Apply overrides only if ALL values can be applied at once or mark
        # the instance with a 'RESTART_REQUIRED' status.
        if not config.does_configuration_need_restart():
            self.guest.apply_overrides(overrides)
        else:
            LOG.debug("Configuration overrides has non-dynamic settings and "
                      "will require restart to take effect.")
            self.update_db(task_status=InstanceTasks.RESTART_REQUIRED)

    def _render_config_dict(self, flavor):
        config = template.SingleInstanceConfigTemplate(
            self.datastore_version, flavor, self.id)
        return dict(config.render_dict())


def create_server_list_matcher(server_list):
    # Returns a method which finds a server from the given list.
    def find_server(instance_id, server_id):
        matches = [server for server in server_list if server.id == server_id]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) < 1:
            # The instance was not found in the list and
            # this can happen if the instance is deleted from
            # nova but still in trove database
            raise exception.ComputeInstanceNotFound(
                instance_id=instance_id, server_id=server_id)
        else:
            # Should never happen, but never say never.
            LOG.error(_LE("Server %(server)s for instance %(instance)s was "
                          "found twice!"), {'server': server_id,
                                            'instance': instance_id})
            raise exception.TroveError(uuid=instance_id)

    return find_server


class Instances(object):
    DEFAULT_LIMIT = CONF.instances_page_size

    @staticmethod
    def load(context, include_clustered, instance_ids=None):

        def load_simple_instance(context, db, status, **kwargs):
            return SimpleInstance(context, db, status)

        if context is None:
            raise TypeError("Argument context not defined.")
        client = create_nova_client(context)
        servers = client.servers.list()
        query_opts = {'tenant_id': context.tenant,
                      'deleted': False}
        if not include_clustered:
            query_opts['cluster_id'] = None
        if instance_ids and len(instance_ids) > 1:
            raise exception.DatastoreOperationNotSupported(
                operation='module-instances', datastore='current')
        if instance_ids:
            query_opts['id'] = instance_ids[0]
        db_infos = DBInstance.find_all(**query_opts)
        limit = utils.pagination_limit(context.limit, Instances.DEFAULT_LIMIT)
        data_view = DBInstance.find_by_pagination('instances', db_infos, "foo",
                                                  limit=limit,
                                                  marker=context.marker)
        next_marker = data_view.next_page_marker

        find_server = create_server_list_matcher(servers)
        for db in db_infos:
            LOG.debug("Checking for db [id=%(db_id)s, "
                      "compute_instance_id=%(instance_id)s].",
                      {'db_id': db.id, 'instance_id': db.compute_instance_id})
        ret = Instances._load_servers_status(load_simple_instance, context,
                                             data_view.collection,
                                             find_server)
        return ret, next_marker

    @staticmethod
    def load_all_by_cluster_id(context, cluster_id, load_servers=True):
        db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                           deleted=False)
        return [load_any_instance(context, db_inst.id,
                                  load_server=load_servers)
                for db_inst in db_instances]

    @staticmethod
    def _load_servers_status(load_instance, context, db_items, find_server):
        ret = []
        for db in db_items:
            server = None
            try:
                # TODO(tim.simpson): Delete when we get notifications working!
                if InstanceTasks.BUILDING == db.task_status:
                    db.server_status = "BUILD"
                    db.addresses = {}
                else:
                    try:
                        server = find_server(db.id, db.compute_instance_id)
                        db.server_status = server.status
                        db.addresses = server.addresses
                    except exception.ComputeInstanceNotFound:
                        db.server_status = "SHUTDOWN"  # Fake it...
                        db.addresses = {}
                # TODO(tim.simpson): End of hack.

                # volumes = find_volumes(server.id)
                datastore_status = InstanceServiceStatus.find_by(
                    instance_id=db.id)
                if not datastore_status.status:  # This should never happen.
                    LOG.error(_LE("Server status could not be read for "
                                  "instance id(%s)."), db.id)
                    continue
                LOG.debug("Server api_status(%s).",
                          datastore_status.status.api_status)
            except exception.ModelNotFoundError:
                LOG.error(_LE("Server status could not be read for "
                              "instance id(%s)."), db.id)
                continue
            ret.append(load_instance(context, db, datastore_status,
                                     server=server))
        return ret


class DBInstance(dbmodels.DatabaseModelBase):
    """Defines the task being executed plus the start time."""

    _data_fields = ['name', 'created', 'compute_instance_id',
                    'task_id', 'task_description', 'task_start_time',
                    'volume_id', 'deleted', 'tenant_id',
                    'datastore_version_id', 'configuration_id', 'slave_of_id',
                    'cluster_id', 'shard_id', 'type']

    def __init__(self, task_status, **kwargs):
        """
        Creates a new persistable entity of the Trove Guest Instance for
        purposes of recording its current state and record of modifications
        :param task_status: the current state details of any activity or error
         that is running on this guest instance (e.g. resizing, deleting)
        :type task_status: trove.instance.tasks.InstanceTask
        """
        kwargs["task_id"] = task_status.code
        kwargs["task_description"] = task_status.db_text
        kwargs["deleted"] = False
        super(DBInstance, self).__init__(**kwargs)
        self.set_task_status(task_status)

    def _validate(self, errors):
        if InstanceTask.from_code(self.task_id) is None:
            errors['task_id'] = "Not valid."
        if self.task_status is None:
            errors['task_status'] = "Cannot be None."

    def get_task_status(self):
        return InstanceTask.from_code(self.task_id)

    def set_task_status(self, value):
        self.task_id = value.code
        self.task_description = value.db_text

    task_status = property(get_task_status, set_task_status)


def persist_instance_fault(notification, event_qualifier):
    """This callback is registered to be fired whenever a
    notification is sent out.
    """
    if "error" == event_qualifier:
        instance_id = notification.payload.get('instance_id')
        message = notification.payload.get(
            'message', 'Missing notification message')
        details = notification.payload.get('exception', [])
        server_type = notification.server_type
        if server_type:
            details.insert(0, "Server type: %s\n" % server_type)
        save_instance_fault(instance_id, message, details)


def save_instance_fault(instance_id, message, details):
    if instance_id:
        try:
            # Make sure it's a valid id - sometimes the error is related
            # to an invalid id and we can't save those
            DBInstance.find_by(id=instance_id, deleted=False)
            msg = utils.format_output(message, truncate_len=255)
            det = utils.format_output(details)
            try:
                fault = DBInstanceFault.find_by(instance_id=instance_id)
                fault.set_info(msg, det)
                fault.save()
            except exception.ModelNotFoundError:
                DBInstanceFault.create(
                    instance_id=instance_id,
                    message=msg, details=det)
        except exception.ModelNotFoundError:
            # We don't need to save anything if the instance id isn't valid
            pass


class DBInstanceFault(dbmodels.DatabaseModelBase):
    _data_fields = ['instance_id', 'message', 'details',
                    'created', 'updated', 'deleted', 'deleted_at']

    def __init__(self, **kwargs):
        super(DBInstanceFault, self).__init__(**kwargs)

    def set_info(self, message, details):
        self.message = message
        self.details = details


class InstanceServiceStatus(dbmodels.DatabaseModelBase):
    _data_fields = ['instance_id', 'status_id', 'status_description',
                    'updated_at']

    def __init__(self, status, **kwargs):
        kwargs["status_id"] = status.code
        kwargs["status_description"] = status.description
        super(InstanceServiceStatus, self).__init__(**kwargs)
        self.set_status(status)

    def _validate(self, errors):
        if self.status is None:
            errors['status'] = "Cannot be None."
        if tr_instance.ServiceStatus.from_code(self.status_id) is None:
            errors['status_id'] = "Not valid."

    def get_status(self):
        """
        Returns the current enumerated status of the Service running on the
        instance
        :return: a ServiceStatus reference indicating the currently stored
        status of the service
        :rtype: trove.common.instance.ServiceStatus
        """
        return tr_instance.ServiceStatus.from_code(self.status_id)

    def set_status(self, value):
        """
        Sets the status of the hosted service
        :param value: current state of the hosted service
        :type value: trove.common.instance.ServiceStatus
        """
        self.status_id = value.code
        self.status_description = value.description

    def save(self):
        self['updated_at'] = utils.utcnow()
        return get_db_api().save(self)

    status = property(get_status, set_status)


def persisted_models():
    return {
        'instance': DBInstance,
        'instance_faults': DBInstanceFault,
        'service_statuses': InstanceServiceStatus,
    }


MYSQL_RESPONSIVE_STATUSES = [tr_instance.ServiceStatuses.RUNNING]
