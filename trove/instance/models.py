# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack Foundation
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

"""Model classes that form the core of instances functionality."""

from datetime import datetime
from novaclient import exceptions as nova_exceptions
from trove.common import cfg
from trove.common import exception
import trove.common.instance as rd_instance
from trove.common.remote import create_dns_client
from trove.common.remote import create_guest_client
from trove.common.remote import create_nova_client
from trove.common.remote import create_cinder_client
from trove.common import utils
from trove.extensions.security_group.models import SecurityGroup
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.datastore import models as datastore_models
from trove.backup.models import Backup
from trove.quota.quota import run_with_quotas
from trove.instance.tasks import InstanceTask
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import api as task_api
from trove.openstack.common import log as logging
from trove.openstack.common import uuidutils
from trove.openstack.common.gettextutils import _


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def load_server(context, instance_id, server_id):
    """Loads a server or raises an exception."""
    client = create_nova_client(context)
    try:
        server = client.servers.get(server_id)
    except nova_exceptions.NotFound:
        LOG.debug("Could not find nova server_id(%s)" % server_id)
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


def validate_volume_size(size):
    if size is None:
        raise exception.VolumeSizeNotSpecified()
    max_size = CONF.max_accepted_volume_size
    if long(size) > max_size:
        msg = ("Volume 'size' cannot exceed maximum "
               "of %d Gb, %s cannot be accepted."
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


# If the compute server is in any of these states we can't perform any
# actions (delete, resize, etc).
SERVER_INVALID_ACTION_STATUSES = ["BUILD", "REBOOT", "REBUILD", "RESIZE"]

# Statuses in which an instance can have an action performed.
VALID_ACTION_STATUSES = ["ACTIVE"]

# Invalid states to contact the agent
AGENT_INVALID_STATUSES = ["BUILD", "REBOOT", "RESIZE"]


class SimpleInstance(object):
    """A simple view of an instance.

    This gets loaded directly from the local database, so its cheaper than
    creating the fully loaded Instance.

    """

    def __init__(self, context, db_info, service_status, root_password=None):
        self.context = context
        self.db_info = db_info
        self.service_status = service_status
        self.root_pass = root_password
        self.ds_version = (datastore_models.DatastoreVersion.
                           load(self.db_info.datastore_version_id))
        self.ds = (datastore_models.Datastore.
                   load(self.ds_version.datastore_id))

    @property
    def addresses(self):
        #TODO(tim.simpson): Review whether we should keep this... its a mess.
        if hasattr(self.db_info, 'addresses'):
            return self.db_info.addresses

    @property
    def created(self):
        return self.db_info.created

    @property
    def flavor_id(self):
        # Flavor ID is a str in the 1.0 API.
        return str(self.db_info.flavor_id)

    @property
    def hostname(self):
        return self.db_info.hostname

    @property
    def id(self):
        return self.db_info.id

    @property
    def tenant_id(self):
        return self.db_info.tenant_id

    @property
    def is_building(self):
        return self.status in [InstanceStatus.BUILD]

    @property
    def is_sql_running(self):
        """True if the service status indicates MySQL is up and running."""
        return self.service_status.status in MYSQL_RESPONSIVE_STATUSES

    @property
    def name(self):
        return self.db_info.name

    @property
    def server_id(self):
        return self.db_info.compute_instance_id

    @property
    def status(self):
        ### Check for taskmanager errors.
        if self.db_info.task_status.is_error:
            return InstanceStatus.ERROR

        ### Check for taskmanager status.
        ACTION = self.db_info.task_status.action
        if 'BUILDING' == ACTION:
            if 'ERROR' == self.db_info.server_status:
                return InstanceStatus.ERROR
            return InstanceStatus.BUILD
        if 'REBOOTING' == ACTION:
            return InstanceStatus.REBOOT
        if 'RESIZING' == ACTION:
            return InstanceStatus.RESIZE

        ### Check for server status.
        if self.db_info.server_status in ["BUILD", "ERROR", "REBOOT",
                                          "RESIZE"]:
            return self.db_info.server_status

        # As far as Trove is concerned, Nova instances in VERIFY_RESIZE should
        # still appear as though they are in RESIZE.
        if self.db_info.server_status in ["VERIFY_RESIZE"]:
            return InstanceStatus.RESIZE

        ### Check if there is a backup running for this instance
        if Backup.running(self.id):
            return InstanceStatus.BACKUP

        ### Report as Shutdown while deleting, unless there's an error.
        if 'DELETING' == ACTION:
            if self.db_info.server_status in ["ACTIVE", "SHUTDOWN", "DELETED"]:
                return InstanceStatus.SHUTDOWN
            else:
                LOG.error(_("While shutting down instance (%(instance)s): "
                            "server had status (%(status)s).") %
                          {'instance': self.id,
                           'status': self.db_info.server_status})
                return InstanceStatus.ERROR

        ### Check against the service status.
        # The service is only paused during a reboot.
        if rd_instance.ServiceStatuses.PAUSED == self.service_status.status:
            return InstanceStatus.REBOOT
        # If the service status is NEW, then we are building.
        if rd_instance.ServiceStatuses.NEW == self.service_status.status:
            return InstanceStatus.BUILD

        # For everything else we can look at the service status mapping.
        return self.service_status.status.api_status

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
    def root_password(self):
        return self.root_pass


class DetailInstance(SimpleInstance):
    """A detailed view of an Instnace.

    This loads a SimpleInstance and then adds additional data for the
    instance from the guest.
    """

    def __init__(self, context, db_info, service_status):
        super(DetailInstance, self).__init__(context, db_info, service_status)
        self._volume_used = None

    @property
    def volume_used(self):
        return self._volume_used

    @volume_used.setter
    def volume_used(self, value):
        self._volume_used = value


def get_db_info(context, id):
    if context is None:
        raise TypeError("Argument context not defined.")
    elif id is None:
        raise TypeError("Argument id not defined.")
    try:
        db_info = DBInstance.find_by(context=context, id=id, deleted=False)
    except exception.NotFound:
        raise exception.NotFound(uuid=id)
    return db_info


def load_any_instance(context, id):
    # Try to load an instance with a server.
    # If that fails, try to load it without the server.
    try:
        return load_instance(BuiltInstance, context, id, needs_server=True)
    except exception.UnprocessableEntity:
        LOG.warn("Could not load instance %s." % id)
        return load_instance(FreshInstance, context, id, needs_server=False)


def load_instance(cls, context, id, needs_server=False):
    db_info = get_db_info(context, id)
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
            #TODO(tim.simpson): Remove this hack when we have notifications!
            db_info.server_status = server.status
            db_info.addresses = server.addresses
        except exception.ComputeInstanceNotFound:
            LOG.error("COMPUTE ID = %s" % db_info.compute_instance_id)
            raise exception.UnprocessableEntity("Instance %s is not ready." %
                                                id)

    service_status = InstanceServiceStatus.find_by(instance_id=id)
    LOG.info("service status=%s" % service_status)
    return cls(context, db_info, server, service_status)


def load_instance_with_guest(cls, context, id):
    db_info = get_db_info(context, id)
    load_simple_instance_server_status(context, db_info)
    service_status = InstanceServiceStatus.find_by(instance_id=id)
    LOG.info("service status=%s" % service_status)
    instance = cls(context, db_info, service_status)
    load_guest_info(instance, context, id)
    return instance


def load_guest_info(instance, context, id):
    if instance.status not in AGENT_INVALID_STATUSES:
        guest = create_guest_client(context, id)
        try:
            volume_info = guest.get_volume_info()
            instance.volume_used = volume_info['used']
        except Exception as e:
            LOG.error(e)
    return instance


class BaseInstance(SimpleInstance):
    """Represents an instance."""

    def __init__(self, context, db_info, server, service_status):
        super(BaseInstance, self).__init__(context, db_info, service_status)
        self.server = server
        self._guest = None
        self._nova_client = None
        self._volume_client = None

    def get_guest(self):
        return create_guest_client(self.context, self.db_info.id)

    def delete(self):
        def _delete_resources():
            if self.is_building:
                raise exception.UnprocessableEntity("Instance %s is not ready."
                                                    % self.id)
            LOG.debug(_("  ... deleting compute id = %s") %
                      self.db_info.compute_instance_id)
            LOG.debug(_(" ... setting status to DELETING."))
            self.update_db(task_status=InstanceTasks.DELETING)
            task_api.API(self.context).delete_instance(self.id)

        deltas = {'instances': -1}
        if CONF.trove_volume_support:
            deltas['volumes'] = -self.volume_size
        return run_with_quotas(self.tenant_id,
                               deltas,
                               _delete_resources)

    def _delete_resources(self, deleted_at):
        pass

    def delete_async(self):
        deleted_at = datetime.utcnow()
        self._delete_resources(deleted_at)
        LOG.debug("Setting instance %s to deleted..." % self.id)
        # Delete guest queue.
        try:
            guest = self.get_guest()
            guest.delete_queue()
        except Exception as ex:
            LOG.warn(ex)
        self.update_db(deleted=True, deleted_at=deleted_at,
                       task_status=InstanceTasks.NONE)
        self.set_servicestatus_deleted()
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
        del_instance.set_status(rd_instance.ServiceStatuses.DELETED)
        del_instance.save()

    @property
    def volume_client(self):
        if not self._volume_client:
            self._volume_client = create_cinder_client(self.context)
        return self._volume_client


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
    def create(cls, context, name, flavor_id, image_id, databases, users,
               datastore, datastore_version, volume_size, backup_id,
               availability_zone=None):

        client = create_nova_client(context)
        try:
            flavor = client.flavors.get(flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=flavor_id)

        deltas = {'instances': 1}
        if CONF.trove_volume_support:
            validate_volume_size(volume_size)
            deltas['volumes'] = volume_size
        else:
            if volume_size is not None:
                raise exception.VolumeNotSupported()
            ephemeral_support = CONF.device_path
            if ephemeral_support and flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=flavor_id)

        if backup_id is not None:
            backup_info = Backup.get_by_id(context, backup_id)
            if backup_info.is_running:
                raise exception.BackupNotCompleteError(backup_id=backup_id)

            if not backup_info.check_swift_object_exist(
                    context,
                    verify_checksum=CONF.verify_swift_checksum_on_restore):
                raise exception.BackupFileNotFound(
                    location=backup_info.location)

        def _create_resources():

            db_info = DBInstance.create(name=name, flavor_id=flavor_id,
                                        tenant_id=context.tenant,
                                        volume_size=volume_size,
                                        datastore_version_id=
                                        datastore_version.id,
                                        task_status=InstanceTasks.BUILDING)
            LOG.debug(_("Tenant %(tenant)s created new "
                        "Trove instance %(db)s...") %
                      {'tenant': context.tenant, 'db': db_info.id})

            service_status = InstanceServiceStatus.create(
                instance_id=db_info.id,
                status=rd_instance.ServiceStatuses.NEW)

            if CONF.trove_dns_support:
                dns_client = create_dns_client(context)
                hostname = dns_client.determine_hostname(db_info.id)
                db_info.hostname = hostname
                db_info.save()

            root_password = None
            if CONF.root_on_create and not backup_id:
                root_password = uuidutils.generate_uuid()

            task_api.API(context).create_instance(db_info.id, name, flavor,
                                                  image_id, databases, users,
                                                  datastore.manager,
                                                  datastore_version.packages,
                                                  volume_size, backup_id,
                                                  availability_zone,
                                                  root_password)

            return SimpleInstance(context, db_info, service_status,
                                  root_password)

        return run_with_quotas(context.tenant,
                               deltas,
                               _create_resources)

    def resize_flavor(self, new_flavor_id):
        self.validate_can_perform_action()
        LOG.debug("resizing instance %s flavor to %s"
                  % (self.id, new_flavor_id))
        # Validate that the flavor can be found and that it isn't the same size
        # as the current one.
        client = create_nova_client(self.context)
        try:
            new_flavor = client.flavors.get(new_flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=new_flavor_id)
        old_flavor = client.flavors.get(self.flavor_id)
        new_flavor_size = new_flavor.ram
        old_flavor_size = old_flavor.ram
        if CONF.trove_volume_support:
            if new_flavor.ephemeral != 0:
                raise exception.LocalStorageNotSupported()
            if new_flavor_size == old_flavor_size:
                raise exception.CannotResizeToSameSize()
        elif CONF.device_path is not None:
            # ephemeral support enabled
            if new_flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=new_flavor_id)
            if (new_flavor_size == old_flavor_size and
                    new_flavor.ephemeral == new_flavor.ephemeral):
                raise exception.CannotResizeToSameSize()

        # Set the task to RESIZING and begin the async call before returning.
        self.update_db(task_status=InstanceTasks.RESIZING)
        LOG.debug("Instance %s set to RESIZING." % self.id)
        task_api.API(self.context).resize_flavor(self.id, old_flavor,
                                                 new_flavor)

    def resize_volume(self, new_size):
        def _resize_resources():
            self.validate_can_perform_action()
            LOG.info("Resizing volume of instance %s..." % self.id)
            if not self.volume_size:
                raise exception.BadRequest("Instance %s has no volume."
                                           % self.id)
            old_size = self.volume_size
            if int(new_size) <= old_size:
                msg = ("The new volume 'size' must be larger than the current "
                       "volume size of '%s'")
                raise exception.BadRequest(msg % old_size)
            # Set the task to Resizing before sending off to the taskmanager
            self.update_db(task_status=InstanceTasks.RESIZING)
            task_api.API(self.context).resize_volume(new_size, self.id)

        new_size_l = long(new_size)
        validate_volume_size(new_size_l)
        return run_with_quotas(self.tenant_id,
                               {'volumes': new_size_l - self.volume_size},
                               _resize_resources)

    def reboot(self):
        self.validate_can_perform_action()
        LOG.info("Rebooting instance %s..." % self.id)
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).reboot(self.id)

    def restart(self):
        self.validate_can_perform_action()
        LOG.info("Restarting MySQL on instance %s..." % self.id)
        # Set our local status since Nova might not change it quick enough.
        #TODO(tim.simpson): Possible bad stuff can happen if this service
        #                   shuts down before it can set status to NONE.
        #                   We need a last updated time to mitigate this;
        #                   after some period of tolerance, we'll assume the
        #                   status is no longer in effect.
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).restart(self.id)

    def migrate(self, host=None):
        self.validate_can_perform_action()
        LOG.info("Migrating instance id = %s, to host = %s" % (self.id, host))
        self.update_db(task_status=InstanceTasks.MIGRATING)
        task_api.API(self.context).migrate(self.id, host)

    def reset_task_status(self):
        LOG.info("Settting task status to NONE on instance %s..." % self.id)
        self.update_db(task_status=InstanceTasks.NONE)

    def validate_can_perform_action(self):
        """
        Raises exception if an instance action cannot currently be performed.
        """
        if self.db_info.server_status != 'ACTIVE':
            status = self.db_info.server_status
        elif self.db_info.task_status != InstanceTasks.NONE:
            status = self.db_info.task_status
        elif not self.service_status.status.action_is_allowed:
            status = self.status
        elif Backup.running(self.id):
            status = InstanceStatus.BACKUP
        else:
            return
        msg = ("Instance is not currently available for an action to be "
               "performed (status was %s)." % status)
        LOG.error(msg)
        raise exception.UnprocessableEntity(msg)


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
            LOG.error(_("Server %(server)s for instance %(instance)s was"
                        "found twice!") % {'server': server_id,
                                           'instance': instance_id})
            raise exception.TroveError(uuid=instance_id)

    return find_server


class Instances(object):
    DEFAULT_LIMIT = CONF.instances_page_size

    @staticmethod
    def load(context):

        def load_simple_instance(context, db, status, **kwargs):
            return SimpleInstance(context, db, status)

        if context is None:
            raise TypeError("Argument context not defined.")
        client = create_nova_client(context)
        servers = client.servers.list()

        db_infos = DBInstance.find_all(tenant_id=context.tenant, deleted=False)
        limit = int(context.limit or Instances.DEFAULT_LIMIT)
        if limit > Instances.DEFAULT_LIMIT:
            limit = Instances.DEFAULT_LIMIT
        data_view = DBInstance.find_by_pagination('instances', db_infos, "foo",
                                                  limit=limit,
                                                  marker=context.marker)
        next_marker = data_view.next_page_marker

        find_server = create_server_list_matcher(servers)
        for db in db_infos:
            LOG.debug("checking for db [id=%s, compute_instance_id=%s]" %
                      (db.id, db.compute_instance_id))
        ret = Instances._load_servers_status(load_simple_instance, context,
                                             data_view.collection,
                                             find_server)
        return ret, next_marker

    @staticmethod
    def _load_servers_status(load_instance, context, db_items, find_server):
        ret = []
        for db in db_items:
            server = None
            try:
                #TODO(tim.simpson): Delete when we get notifications working!
                if InstanceTasks.BUILDING == db.task_status:
                    db.server_status = "BUILD"
                else:
                    try:
                        server = find_server(db.id, db.compute_instance_id)
                        db.server_status = server.status
                    except exception.ComputeInstanceNotFound:
                        db.server_status = "SHUTDOWN"  # Fake it...
                #TODO(tim.simpson): End of hack.

                #volumes = find_volumes(server.id)
                status = InstanceServiceStatus.find_by(instance_id=db.id)
                LOG.info(_("Server api_status(%s)") %
                         status.status.api_status)
                if not status.status:  # This should never happen.
                    LOG.error(_("Server status could not be read for "
                                "instance id(%s)") % db.id)
                    continue
            except exception.ModelNotFoundError:
                LOG.error(_("Server status could not be read for "
                            "instance id(%s)") % db.id)
                continue
            ret.append(load_instance(context, db, status, server=server))
        return ret


class DBInstance(dbmodels.DatabaseModelBase):
    """Defines the task being executed plus the start time."""

    #TODO(tim.simpson): Add start time.

    _data_fields = ['name', 'created', 'compute_instance_id',
                    'task_id', 'task_description', 'task_start_time',
                    'volume_id', 'deleted', 'tenant_id',
                    'datastore_version_id']

    def __init__(self, task_status, **kwargs):
        kwargs["task_id"] = task_status.code
        kwargs["task_description"] = task_status.db_text
        kwargs["deleted"] = False
        super(DBInstance, self).__init__(**kwargs)
        self.set_task_status(task_status)

    def _validate(self, errors):
        if InstanceTask.from_code(self.task_id) is None:
            errors['task_id'] = "Not valid."
        if self.task_status is None:
            errors['task_status'] = "Cannot be none."

    def get_task_status(self):
        return InstanceTask.from_code(self.task_id)

    def set_task_status(self, value):
        self.task_id = value.code
        self.task_description = value.db_text

    task_status = property(get_task_status, set_task_status)


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
            errors['status'] = "Cannot be none."
        if rd_instance.ServiceStatus.from_code(self.status_id) is None:
            errors['status_id'] = "Not valid."

    def get_status(self):
        return rd_instance.ServiceStatus.from_code(self.status_id)

    def set_status(self, value):
        self.status_id = value.code
        self.status_description = value.description

    def save(self):
        self['updated_at'] = utils.utcnow()
        return get_db_api().save(self)

    status = property(get_status, set_status)


def persisted_models():
    return {
        'instance': DBInstance,
        'service_statuses': InstanceServiceStatus,
    }


MYSQL_RESPONSIVE_STATUSES = [rd_instance.ServiceStatuses.RUNNING]
