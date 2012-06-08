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
import logging
import netaddr

from reddwarf import db

from novaclient import exceptions as nova_exceptions
from reddwarf.common import config
from reddwarf.common import exception as rd_exceptions
from reddwarf.common import pagination
from reddwarf.common import utils
from reddwarf.common.models import ModelBase
from novaclient import exceptions as nova_exceptions
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_guest_client
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.utils import poll_until
from reddwarf.instance.tasks import InstanceTask
from reddwarf.instance.tasks import InstanceTasks
from reddwarf.taskmanager import api as task_api


from eventlet import greenthread
from reddwarf.instance.views import get_ip_address


CONFIG = config.Config
LOG = logging.getLogger(__name__)


def load_server_with_volumes(context, instance_id, server_id):
    """Loads a server or raises an exception."""
    client = create_nova_client(context)
    try:
        server = client.servers.get(server_id)
        volumes = load_volumes(context, server_id, client=client)
    except nova_exceptions.NotFound, e:
        LOG.debug("Could not find nova server_id(%s)" % server_id)
        raise rd_exceptions.ComputeInstanceNotFound(instance_id=instance_id,
                                                  server_id=server_id)
    except nova_exceptions.ClientException, e:
        raise rd_exceptions.ReddwarfError(str(e))
    return server, volumes


def load_volumes(context, server_id, client=None):
    volume_support = config.Config.get("reddwarf_volume_support", 'False')
    if utils.bool_from_string(volume_support):
        if client is None:
            client = create_nova_client(context)
        volume_client = create_nova_volume_client(context)
        try:
            volumes = []
            volumes_info = client.volumes.get_server_volumes(server_id)
            volume_ids = [attachments.volumeId for attachments in
                          volumes_info]
            for volume_id in volume_ids:
                volume_info = volume_client.volumes.get(volume_id)
                volume = {'id': volume_info.id,
                          'size': volume_info.size}
                if volume_info.attachments:
                    volume['mountpoint'] = volume_info.attachments[0]['device']
                volumes.append(volume)
        except nova_exceptions.NotFound, e:
            LOG.debug("Could not find nova server_id(%s)" % server_id)
            raise rd_exceptions.VolumeAttachmentsNotFound(server_id=server_id)
        except nova_exceptions.ClientException, e:
            raise rd_exceptions.ReddwarfError(str(e))
        return volumes
    return None


# This probably should not happen here. Seems like it should
# be in an extension instead
def populate_databases(dbs):
    """
    Create a serializable request with user provided data
    for creating new databases.
    """
    from reddwarf.guestagent.db import models as guest_models
    try:
        databases = []
        for database in dbs:
            mydb = guest_models.MySQLDatabase()
            mydb.name = database.get('name', '')
            mydb.character_set = database.get('character_set', '')
            mydb.collate = database.get('collate', '')
            databases.append(mydb.serialize())
        return databases
    except ValueError as ve:
        raise rd_exceptions.BadRequest(ve.message)


class InstanceStatus(object):

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    BUILD = "BUILD"
    FAILED = "FAILED"
    REBOOT = "REBOOT"
    RESIZE = "RESIZE"
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"


# If the compute server is in any of these states we can't perform any
# actions (delete, resize, etc).
SERVER_INVALID_ACTION_STATUSES = ["BUILD", "REBOOT", "REBUILD"]

# Statuses in which an instance can have an action performed.
VALID_ACTION_STATUSES = ["ACTIVE"]


class SimpleInstance(object):
    """

    Simple model is a quick hack for when server/volumes is not available, and
    all we have is database info. Example is create instance response, when the
    async call to server/volume may not have completed yet.

    """

    def __init__(self, context, db_info, service_status):
        self.context = context
        self.db_info = db_info
        self.service_status = service_status
        self.volumes = [{'size': self.db_info.volume_size }]

    @staticmethod
    def load(context, id):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument id not defined.")
        try:
            db_info = DBInstance.find_by(id=id)
        except rd_exceptions.NotFound:
            raise rd_exceptions.NotFound(uuid=id)
        task_status = db_info.task_status
        service_status = InstanceServiceStatus.find_by(instance_id=id)
        LOG.info("service status=%s" % service_status)
        return SimpleInstance(context, db_info, service_status)

    @property
    def name(self):
        return self.db_info.name

    @property
    def id(self):
        return self.db_info.id

    @property
    def hostname(self):
        return self.db_info.hostname

    @property
    def status(self):
        # If the service status is NEW, then we are building.
        if ServiceStatuses.NEW == self.service_status.status:
            return InstanceStatus.BUILD

    @property
    def created(self):
        return self.db_info.created

    @property
    def updated(self):
        return self.db_info.updated

    @property
    def addresses(self):
        return None

    @property
    def is_building(self):
        return self.status in [InstanceStatus.BUILD]

    @property
    def is_sql_running(self):
        """True if the service status indicates MySQL is up and running."""
        return self.service_status.status in MYSQL_RESPONSIVE_STATUSES

    @property
    def links(self):
        """
        The links here are just used for structural format. The actual link is
        created in the views by replacing the matching pieces from the request
        """
        links = [
            {
                "href": "https://localhost/v1.0/tenant_id/instances/instance_id",
                "rel": "self"
            },
            {
                "href": "https://localhost/instances/instance_id",
                "rel": "bookmark"
            }
        ]
        return links

    @property
    def flavor_links(self):
        links = [
            {
                "href": "https://localhost/v1.0/tenant_id/flavors/flavor_id",
                "rel": "self"
            },
            {
                "href": "https://localhost/flavors/flavor_id",
                "rel": "bookmark"
            }
        ]
        return links

    def restart(self):
        # Just so it doesnt blow if restart is accidentally called
        raise rd_exceptions.UnprocessableEntity("Instance %s is not ready."
                                    % self.id)

    def delete(self):
        # Just so it doesnt blow if delete is accidentally called
        raise rd_exceptions.UnprocessableEntity("Instance %s is not ready."
                                    % self.id)


class Instance(SimpleInstance):
    """Represents an instance.

    The life span of this object should be limited. Do not store them or
    pass them between threads.
    """

    def __init__(self, context, db_info, server, service_status, volumes):
        super(Instance, self).__init__(context, db_info, service_status)
        self.server = server
        self.volumes = volumes

    @staticmethod
    def load(context, id):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument id not defined.")
        try:
            db_info = DBInstance.find_by(id=id)
        except rd_exceptions.NotFound:
            raise rd_exceptions.NotFound(uuid=id)

        task_status = db_info.task_status
        service_status = InstanceServiceStatus.find_by(instance_id=id)
        LOG.info("service status=%s" % service_status)
        if db_info.compute_instance_id is None:
            LOG.debug("Missing server_id for instance %s " % db_info.id)
            # TODO: Should it raise exception or return SimpleInstance?
            # If I return SimpleInstance, somebody will invoke delete on it and
            # it will be method not found.
            return SimpleInstance(context, db_info, service_status)

        server, volumes = load_server_with_volumes(context, db_info.id,
            db_info.compute_instance_id)
        return Instance(context, db_info, server, service_status, volumes)

    def delete(self, force=False):
        if not force and self.server.status in SERVER_INVALID_ACTION_STATUSES:
            raise rd_exceptions.UnprocessableEntity("Instance %s is not ready."
                                                    % self.id)
        LOG.debug(_("  ... deleting compute id = %s") %
                  self.server.id)
        LOG.debug(_(" ... setting status to DELETING."))
        self.db_info.task_status = InstanceTasks.DELETING
        self.db_info.save()
        task_api.API(self.context).delete_instance(self.id)

    @classmethod
    def create(cls, context, name, flavor_ref, image_id,
               databases, service_type, volume_size):
        flavor_id = utils.get_id_from_href(flavor_ref)
        db_info = DBInstance.create(name=name, volume_size=volume_size,
            flavor_id =flavor_id, task_status=InstanceTasks.NONE)
        LOG.debug(_("Created new Reddwarf instance %s...") % db_info.id)

        task_api.API(context).create_instance(db_info.id, name,
                                flavor_ref, image_id, databases, service_type,
                                volume_size)
        # Defaults the hostname to instance name of dns is disabled.
        dns_client = create_dns_client(context)
        dns_client.update_hostname(db_info)

        #Check to see if a New status has already been created
        service_status = InstanceServiceStatus.get_by(instance_id=db_info.id)
        if service_status is None:
            service_status = InstanceServiceStatus.create(
                                    instance_id=db_info.id,
                                    status=ServiceStatuses.NEW)

        return SimpleInstance(context, db_info, service_status)

    def get_guest(self):
        return create_guest_client(self.context, self.db_info.id)

    @property
    def is_building(self):
        return self.status in [InstanceStatus.BUILD]

    @property
    def is_sql_running(self):
        """True if the service status indicates MySQL is up and running."""
        return self.service_status.status in MYSQL_RESPONSIVE_STATUSES

    @property
    def name(self):
        return self.server.name

    @property
    def status(self):
        #TODO(tim.simpson): As we enter more advanced cases dealing with
        # timeouts determine if the task_status should be integrated here
        # or removed entirely.
        if InstanceTasks.REBOOTING == self.db_info.task_status:
            return InstanceStatus.REBOOT
        if InstanceTasks.RESIZING == self.db_info.task_status:
            return InstanceStatus.RESIZE
        # If the server is in any of these states they take precedence.
        if self.server.status in ["BUILD", "ERROR", "REBOOT", "RESIZE"]:
            return self.server.status
        # The service is only paused during a reboot.
        if ServiceStatuses.PAUSED == self.service_status.status:
            return InstanceStatus.REBOOT
        # If the service status is NEW, then we are building.
        if ServiceStatuses.NEW == self.service_status.status:
            return InstanceStatus.BUILD
        if InstanceTasks.DELETING == self.db_info.task_status:
            if self.server.status in ["ACTIVE", "SHUTDOWN"]:
                return InstanceStatus.SHUTDOWN
            else:
                LOG.error(_("While shutting down instance (%s): server had "
                          " status (%s).") % (self.id, self.server.status))
                return InstanceStatus.ERROR
        # For everything else we can look at the service status mapping.
        return self.service_status.status.api_status

    @property
    def flavor(self):
        return self.server.flavor

    @property
    def links(self):
        return self.server.links

    @property
    def addresses(self):
        #TODO(tim.simpson): Review whether we should be returning the server
        # addresses.
        return self.server.addresses

    @staticmethod
    def _build_links(links):
        #TODO(tim.simpson): Don't return the Nova port.
        """Build the links for the instance"""
        for link in links:
            link['href'] = link['href'].replace('servers', 'instances')
        return links

    def _validate_can_perform_action(self):
        """
        Raises an exception if the instance can't perform an action.
        """
        if self.status not in VALID_ACTION_STATUSES:
            msg = "Instance is not currently available for an action to be " \
                  "performed. Status [%s]"
            LOG.debug(_(msg) % self.status)
            raise rd_exceptions.UnprocessableEntity(_(msg) % self.status)

    def resize_flavor(self, new_flavor_id):
        self.validate_can_perform_resize()
        LOG.debug("resizing instance %s flavor to %s"
                  % (self.id, new_flavor_id))
        # Validate that the flavor can be found and that it isn't the same size
        # as the current one.
        client = create_nova_client(self.context)
        try:
            new_flavor = client.flavors.get(new_flavor_id)
        except nova_exceptions.NotFound:
            raise rd_exceptions.FlavorNotFound(uuid=new_flavor_id)
        old_flavor = client.flavors.get(self.server.flavor['id'])
        new_flavor_size = new_flavor.ram
        old_flavor_size = old_flavor.ram
        if new_flavor_size == old_flavor_size:
            raise rd_exceptions.CannotResizeToSameSize()

        # Set the task to RESIZING and begin the async call before returning.
        self.db_info.task_status = InstanceTasks.RESIZING
        self.db_info.save()
        LOG.debug("Instance %s set to RESIZING." % self.id)
        task_api.API(self.context).resize_flavor(self.id, new_flavor_id,
                    old_flavor_size, new_flavor_size)

    def resize_volume(self, new_size):
        LOG.info("Resizing volume of instance %s..." % self.id)
        if len(self.volumes) != 1:
            raise rd_exceptions.BadRequest("The instance has %r attached "
                                           "volumes" % len(self.volumes))
        old_size = self.volumes[0]['size']
        if int(new_size) <= old_size:
            raise rd_exceptions.BadRequest("The new volume 'size' cannot be "
                        "less than the current volume size of '%s'" % old_size)
        # Set the task to Resizing before sending off to the taskmanager
        self.db_info.task_status = InstanceTasks.RESIZING
        self.db_info.save()
        task_api.API(self.context).resize_volume(new_size, self.id)


    def restart(self):
        if self.server.status in SERVER_INVALID_ACTION_STATUSES:
            msg = _("Restart instance not allowed while instance %s is in %s "
                    "status.") % (self.id, instance_state)
            LOG.debug(msg)
            # If the state is building then we throw an exception back
            raise rd_exceptions.UnprocessableEntity(msg)
        else:
            LOG.info("Restarting instance %s..." % self.id)
        # Set our local status since Nova might not change it quick enough.
        #TODO(tim.simpson): Possible bad stuff can happen if this service
        #                   shuts down before it can set status to NONE.
        #                   We need a last updated time to mitigate this;
        #                   after some period of tolerance, we'll assume the
        #                   status is no longer in effect.
        self.db_info.task_status = InstanceTasks.REBOOTING
        self.db_info.save()
        try:
            self.get_guest().restart()
        except rd_exceptions.GuestError:
            LOG.error("Failure to restart MySQL.")
        finally:
            self.db_info.task_status = InstanceTasks.NONE
            self.db_info.save()

    def validate_can_perform_restart_or_reboot(self):
        """
        Raises exception if an instance action cannot currently be performed.
        """
        if self.db_info.task_status != InstanceTasks.NONE or \
           not self.service_status.status.restart_is_allowed:
            msg = "Instance is not currently available for an action to be " \
                  "performed (task status was %s, service status was %s)." \
                  % (self.db_info.task_status, self.service_status.status)
            LOG.error(msg)
            raise rd_exceptions.UnprocessableEntity(msg)

    def validate_can_perform_resize(self):
        """
        Raises exception if an instance action cannot currently be performed.
        """
        if self.status != InstanceStatus.ACTIVE:
            msg = "Instance is not currently available for an action to be " \
                  "performed (status was %s)." % self.status
            LOG.error(msg)
            raise rd_exceptions.UnprocessableEntity(msg)


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
            raise rd_exceptions.ComputeInstanceNotFound(
                instance_id=instance_id, server_id=server_id)
        else:
            # Should never happen, but never say never.
            LOG.error(_("Server %s for instance %s was found twice!")
                  % (server_id, instance_id))
            raise rd_exceptions.ReddwarfError(uuid=instance_id)
    return find_server


def create_volumes_list_matcher(volume_list):
    # Returns a method which finds a volume from the given list.
    def find_volumes(server_id):
        return [{'id': volume.id, 'size': volume.size}
                    for volume in volume_list
                        if server_id in [attachment["server_id"]
                            for attachment in volume.attachments]]
    return find_volumes


class Instances(object):

    DEFAULT_LIMIT = int(config.Config.get('instances_page_size', '20'))

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        client = create_nova_client(context)
        servers = client.servers.list()
        volume_client = create_nova_volume_client(context)
        try:
            volumes = volume_client.volumes.list(detailed=False)
        except nova_exceptions.NotFound:
            volumes = []

        db_infos = DBInstance.find_all()
        limit = int(context.limit or Instances.DEFAULT_LIMIT)
        if limit > Instances.DEFAULT_LIMIT:
            limit = Instances.DEFAULT_LIMIT
        data_view = DBInstance.find_by_pagination('instances', db_infos, "foo",
                                                  limit=limit,
                                                  marker=context.marker)
        next_marker = data_view.next_page_marker

        ret = []
        find_server = create_server_list_matcher(servers)
        find_volumes = create_volumes_list_matcher(volumes)
        for db in db_infos:
            LOG.debug("checking for db [id=%s, compute_instance_id=%s]" %
                      (db.id, db.compute_instance_id))
        for db in data_view.collection:
            try:
                # TODO(hub-cap): Figure out if this is actually correct.
                # We are not sure if we should be doing some validation.
                # Basically if the server find returns nothing, but we
                # have something, there is a mismatch between what the
                # nova db has compared to what we have. We should have
                # a way to handle this.
                server = find_server(db.id, db.compute_instance_id)
                volumes = find_volumes(server.id)
                status = InstanceServiceStatus.find_by(instance_id=db.id)
                LOG.info(_("Server api_status(%s)") %
                           (status.status.api_status))

                if not status.status:
                    LOG.info(_("Server status could not be read for "
                               "instance id(%s)") % (db.compute_instance_id))
                    continue
                if status.status.api_status in ['SHUTDOWN']:
                    LOG.info(_("Server was shutdown id(%s)") %
                           (db.compute_instance_id))
                    continue
            except rd_exceptions.ComputeInstanceNotFound:
                LOG.info(_("Could not find server %s") %
                           db.compute_instance_id)
                continue
            except ModelNotFoundError:
                LOG.info(_("Status entry not found either failed to start "
                           "or instance was deleted"))
                continue
            ret.append(Instance(context, db, server, status, volumes))
        return ret, next_marker


class DatabaseModelBase(ModelBase):
    _auto_generated_attrs = ['id']

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        values['created'] = utils.utcnow()
        instance = cls(**values).save()
        if not instance.is_valid():
            raise InvalidModelError(instance.errors)
        return instance

    def save(self):
        if not self.is_valid():
            raise InvalidModelError(self.errors)
        self['updated'] = utils.utcnow()
        LOG.debug(_("Saving %s: %s") %
            (self.__class__.__name__, self.__dict__))
        return db.db_api.save(self)

    def delete(self):
        self['updated'] = utils.utcnow()
        LOG.debug(_("Deleting %s: %s") %
            (self.__class__.__name__, self.__dict__))
        return db.db_api.delete(self)

    def __init__(self, **kwargs):
        self.merge_attributes(kwargs)
        if not self.is_valid():
            raise InvalidModelError(self.errors)

    def merge_attributes(self, values):
        """dict.update() behaviour."""
        for k, v in values.iteritems():
            self[k] = v

    @classmethod
    def find_by(cls, **conditions):
        model = cls.get_by(**conditions)
        if model is None:
            raise ModelNotFoundError(_("%s Not Found") % cls.__name__)
        return model

    @classmethod
    def get_by(cls, **kwargs):
        return db.db_api.find_by(cls, **cls._process_conditions(kwargs))

    @classmethod
    def find_all(cls, **kwargs):
        return db.db_query.find_all(cls, **cls._process_conditions(kwargs))

    @classmethod
    def _process_conditions(cls, raw_conditions):
        """Override in inheritors to format/modify any conditions."""
        return raw_conditions

    @classmethod
    def find_by_pagination(cls, collection_type, collection_query,
                            paginated_url, **kwargs):
        elements, next_marker = collection_query.paginated_collection(**kwargs)

        return pagination.PaginatedDataView(collection_type,
                                            elements,
                                            paginated_url,
                                            next_marker)


class DBInstance(DatabaseModelBase):
    """Defines the task being executed plus the start time."""

    #TODO(tim.simpson): Add start time.

    _data_fields = ['name', 'created', 'compute_instance_id',
                    'task_id', 'task_description', 'task_start_time',
                    'volume_id']

    def __init__(self, task_status=None, **kwargs):
        kwargs["task_id"] = task_status.code
        kwargs["task_description"] = task_status.db_text
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


class ServiceImage(DatabaseModelBase):
    """Defines the status of the service being run."""

    _data_fields = ['service_name', 'image_id']


class InstanceServiceStatus(DatabaseModelBase):

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


class InvalidModelError(rd_exceptions.ReddwarfError):

    message = _("The following values are invalid: %(errors)s")

    def __init__(self, errors, message=None):
        super(InvalidModelError, self).__init__(message, errors=errors)


class ModelNotFoundError(rd_exceptions.ReddwarfError):

    message = _("Not Found")


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

    @property
    def restart_is_allowed(self):
        return self._code in [ServiceStatuses.RUNNING._code,
            ServiceStatuses.SHUTDOWN._code, ServiceStatuses.CRASHED._code,
            ServiceStatuses.BLOCKED._code]

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
