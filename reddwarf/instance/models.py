# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Model classes that form the core of instances functionality."""

import eventlet
import netaddr

from datetime import datetime
from novaclient import exceptions as nova_exceptions
from reddwarf.common import cfg
from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_guest_client
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.db import models as dbmodels
from reddwarf.instance.tasks import InstanceTask
from reddwarf.instance.tasks import InstanceTasks
from reddwarf.guestagent import models as agent_models
from reddwarf.taskmanager import api as task_api
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _


from eventlet import greenthread


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def load_server(context, instance_id, server_id):
    """Loads a server or raises an exception."""
    client = create_nova_client(context)
    try:
        server = client.servers.get(server_id)
    except nova_exceptions.NotFound as e:
        LOG.debug("Could not find nova server_id(%s)" % server_id)
        raise exception.ComputeInstanceNotFound(instance_id=instance_id,
                                                server_id=server_id)
    except nova_exceptions.ClientException, e:
        raise exception.ReddwarfError(str(e))
    return server


class InstanceStatus(object):

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    BUILD = "BUILD"
    FAILED = "FAILED"
    REBOOT = "REBOOT"
    RESIZE = "RESIZE"
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"


def validate_volume_size(size):
    max_size = CONF.max_accepted_volume_size
    if long(size) > max_size:
        msg = ("Volume 'size' cannot exceed maximum "
               "of %d Gb, %s cannot be accepted."
               % (max_size, size))
        raise exception.VolumeQuotaExceeded(msg)


def run_with_quotas(tenant_id, deltas, f):
    """ Quota wrapper """

    from reddwarf.quota.quota import QUOTAS as quota_engine
    reservations = quota_engine.reserve(tenant_id, **deltas)
    result = None
    try:
        result = f()
    except:
        quota_engine.rollback(reservations)
        raise
    else:
        quota_engine.commit(reservations)
    return result


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
        except nova_exceptions.NotFound, e:
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

    def __init__(self, context, db_info, service_status):
        self.context = context
        self.db_info = db_info
        self.service_status = service_status

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
        return self.db_info.flavor_id

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

        ### Report as Shutdown while deleting, unless there's an error.
        if 'DELETING' == ACTION:
            if self.db_info.server_status in ["ACTIVE", "SHUTDOWN", "DELETED"]:
                return InstanceStatus.SHUTDOWN
            else:
                msg = _("While shutting down instance (%s): server had "
                        "status (%s).")
                LOG.error(msg % (self.id, self.db_info.server_status))
                return InstanceStatus.ERROR

        ### Check against the service status.
        # The service is only paused during a reboot.
        if ServiceStatuses.PAUSED == self.service_status.status:
            return InstanceStatus.REBOOT
        # If the service status is NEW, then we are building.
        if ServiceStatuses.NEW == self.service_status.status:
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
        db_info = DBInstance.find_by(id=id, deleted=False)
    except exception.NotFound:
        raise exception.NotFound(uuid=id)
    except exception.ModelNotFoundError:
        raise exception.NotFound(uuid=id)
    if not context.is_admin and db_info.tenant_id != context.tenant:
        LOG.error("Tenant %s tried to access instance %s, owned by %s."
                  % (context.tenant, id, db_info.tenant_id))
        raise exception.NotFound(uuid=id)
    return db_info


def load_any_instance(context, id):
    # Try to load an instance with a server.
    # If that fails, try to load it without the server.
    try:
        return load_instance(BuiltInstance, context, id, needs_server=True)
    except exception.UnprocessableEntity as upe:
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
            instance.volume_used = guest.get_volume_info()['used']
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

        return run_with_quotas(self.tenant_id,
                               {'instances': -1,
                                'volumes': -self.volume_size},
                               _delete_resources)

    def _delete_resources(self):
        pass

    def delete_async(self):
        self._delete_resources()
        LOG.debug("Setting instance %s to deleted..." % self.id)
        # Delete guest queue.
        try:
            guest = self.get_guest()
            guest.delete_queue()
        except Exception as ex:
            LOG.warn(ex)
        time_now = datetime.now()
        self.update_db(deleted=True, deleted_at=time_now,
                       task_status=InstanceTasks.NONE)

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

    @property
    def volume_client(self):
        if not self._volume_client:
            self._volume_client = create_nova_volume_client(self.context)
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

    def _delete_resources(self):
        pass

    @classmethod
    def create(cls, context, name, flavor_id, image_id,
               databases, users, service_type, volume_size):
        def _create_resources():
            client = create_nova_client(context)
            try:
                flavor = client.flavors.get(flavor_id)
            except nova_exceptions.NotFound:
                raise exception.FlavorNotFound(uuid=flavor_id)

            db_info = DBInstance.create(name=name, flavor_id=flavor_id,
                                        tenant_id=context.tenant,
                                        volume_size=volume_size,
                                        task_status=InstanceTasks.BUILDING)
            LOG.debug(_("Tenant %s created new Reddwarf instance %s...")
                      % (context.tenant, db_info.id))

            service_status = InstanceServiceStatus.create(
                instance_id=db_info.id,
                status=ServiceStatuses.NEW)

            if CONF.reddwarf_dns_support:
                dns_client = create_dns_client(context)
                hostname = dns_client.determine_hostname(db_info.id)
                db_info.hostname = hostname
                db_info.save()

            task_api.API(context).create_instance(db_info.id, name, flavor_id,
                                                  flavor.ram, image_id,
                                                  databases, users,
                                                  service_type, volume_size)

            return SimpleInstance(context, db_info, service_status)

        validate_volume_size(volume_size)
        return run_with_quotas(context.tenant,
                               {'instances': 1, 'volumes': volume_size},
                               _create_resources)

    def resize_flavor(self, new_flavor_id):
        self._validate_can_perform_action()
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
        if new_flavor_size == old_flavor_size:
            raise exception.CannotResizeToSameSize()

        # Set the task to RESIZING and begin the async call before returning.
        self.update_db(task_status=InstanceTasks.RESIZING)
        LOG.debug("Instance %s set to RESIZING." % self.id)
        task_api.API(self.context).resize_flavor(self.id, new_flavor_id,
                                                 old_flavor_size,
                                                 new_flavor_size)

    def resize_volume(self, new_size):
        def _resize_resources():
            self._validate_can_perform_action()
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
        self._validate_can_perform_action()
        LOG.info("Rebooting instance %s..." % self.id)
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).reboot(self.id)

    def restart(self):
        self._validate_can_perform_action()
        LOG.info("Restarting MySQL on instance %s..." % self.id)
        # Set our local status since Nova might not change it quick enough.
        #TODO(tim.simpson): Possible bad stuff can happen if this service
        #                   shuts down before it can set status to NONE.
        #                   We need a last updated time to mitigate this;
        #                   after some period of tolerance, we'll assume the
        #                   status is no longer in effect.
        self.update_db(task_status=InstanceTasks.REBOOTING)
        task_api.API(self.context).restart(self.id)

    def migrate(self):
        self._validate_can_perform_action()
        LOG.info("Migrating instance %s..." % self.id)
        self.update_db(task_status=InstanceTasks.MIGRATING)
        task_api.API(self.context).migrate(self.id)

    def reset_task_status(self):
        LOG.info("Settting task status to NONE on instance %s..." % self.id)
        self.update_db(task_status=InstanceTasks.NONE)

    def _validate_can_perform_action(self):
        """
        Raises exception if an instance action cannot currently be performed.
        """
        status = None
        if self.db_info.server_status != 'ACTIVE':
            status = self.db_info.server_status
        elif self.db_info.task_status != InstanceTasks.NONE:
            status = self.db_info.task_status
        elif not self.service_status.status.action_is_allowed:
            status = self.status
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
            # nova but still in reddwarf database
            raise exception.ComputeInstanceNotFound(
                instance_id=instance_id, server_id=server_id)
        else:
            # Should never happen, but never say never.
            LOG.error(_("Server %s for instance %s was found twice!") %
                      (server_id, instance_id))
            raise exception.ReddwarfError(uuid=instance_id)
    return find_server


class Instances(object):

    DEFAULT_LIMIT = CONF.instances_page_size

    @staticmethod
    def load(context):

        def load_simple_instance(context, db, status):
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
                         (status.status.api_status))
                if not status.status:  # This should never happen.
                    LOG.error(_("Server status could not be read for "
                                "instance id(%s)") % (db.id))
                    continue
            except exception.ModelNotFoundError:
                LOG.error(_("Server status could not be read for "
                            "instance id(%s)") % (db.id))
                continue
            ret.append(load_instance(context, db, status))
        return ret


class DBInstance(dbmodels.DatabaseModelBase):
    """Defines the task being executed plus the start time."""

    #TODO(tim.simpson): Add start time.

    _data_fields = ['name', 'created', 'compute_instance_id',
                    'task_id', 'task_description', 'task_start_time',
                    'volume_id', 'deleted', 'tenant_id']

    def __init__(self, task_status=None, **kwargs):
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


class ServiceImage(dbmodels.DatabaseModelBase):
    """Defines the status of the service being run."""

    _data_fields = ['service_name', 'image_id']


class InstanceServiceStatus(dbmodels.DatabaseModelBase):

    _data_fields = ['instance_id', 'status_id', 'status_description']

    def __init__(self, status=None, **kwargs):
        kwargs["status_id"] = status.code
        kwargs["status_description"] = status.description
        super(InstanceServiceStatus, self).__init__(**kwargs)
        self.set_status(status)

    def _validate(self, errors):
        if self.status is None:
            errors['status'] = "Cannot be none."
        if ServiceStatus.from_code(self.status_id) is None:
            errors['status_id'] = "Not valid."

    def get_status(self):
        return ServiceStatus.from_code(self.status_id)

    def set_status(self, value):
        self.status_id = value.code
        self.status_description = value.description

    status = property(get_status, set_status)


def persisted_models():
    return {
        'instance': DBInstance,
        'service_image': ServiceImage,
        'service_statuses': InstanceServiceStatus,
    }


class ServiceStatus(object):
    """Represents the status of the app and in some rare cases the agent.

    Code and description are what is stored in the database. "api_status"
    refers to the status which comes back from the REST API.
    """
    _lookup = {}

    def __init__(self, code, description, api_status):
        self._code = code
        self._description = description
        self._api_status = api_status
        ServiceStatus._lookup[code] = self

    @property
    def action_is_allowed(self):
        allowed_statuses = [
            ServiceStatuses.RUNNING._code,
            ServiceStatuses.SHUTDOWN._code,
            ServiceStatuses.CRASHED._code,
            ServiceStatuses.BLOCKED._code,
        ]
        return self._code in allowed_statuses

    @property
    def api_status(self):
        return self._api_status

    @property
    def code(self):
        return self._code

    @property
    def description(self):
        return self._description

    def __eq__(self, other):
        if not isinstance(other, ServiceStatus):
            return False
        return self.code == other.code

    @staticmethod
    def from_code(code):
        if code not in ServiceStatus._lookup:
            msg = 'Status code %s is not a valid ServiceStatus integer code.'
            raise ValueError(msg % code)
        return ServiceStatus._lookup[code]

    @staticmethod
    def from_description(desc):
        all_items = ServiceStatus._lookup.items()
        status_codes = [code for (code, status) in all_items if status == desc]
        if not status_codes:
            msg = 'Status description %s is not a valid ServiceStatus.'
            raise ValueError(msg % desc)
        return ServiceStatus._lookup[status_codes[0]]

    @staticmethod
    def is_valid_code(code):
        return code in ServiceStatus._lookup

    def __str__(self):
        return self._description


class ServiceStatuses(object):
    RUNNING = ServiceStatus(0x01, 'running', 'ACTIVE')
    BLOCKED = ServiceStatus(0x02, 'blocked', 'BLOCKED')
    PAUSED = ServiceStatus(0x03, 'paused', 'SHUTDOWN')
    SHUTDOWN = ServiceStatus(0x04, 'shutdown', 'SHUTDOWN')
    CRASHED = ServiceStatus(0x06, 'crashed', 'SHUTDOWN')
    FAILED = ServiceStatus(0x08, 'failed to spawn', 'FAILED')
    BUILDING = ServiceStatus(0x09, 'building', 'BUILD')
    UNKNOWN = ServiceStatus(0x16, 'unknown', 'ERROR')
    NEW = ServiceStatus(0x17, 'new', 'NEW')


MYSQL_RESPONSIVE_STATUSES = [ServiceStatuses.RUNNING]


# Dissuade further additions at run-time.
ServiceStatus.__init__ = None
