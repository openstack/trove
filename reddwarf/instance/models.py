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

import logging
import netaddr

from reddwarf import db

from reddwarf.common import config
from reddwarf.common import exception as rd_exceptions
from reddwarf.common import utils
from reddwarf.instance.tasks import InstanceTask
from reddwarf.instance.tasks import InstanceTasks
from reddwarf.common.models import ModelBase
from novaclient import exceptions as nova_exceptions
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.remote import create_guest_client


from eventlet import greenthread


CONFIG = config.Config
LOG = logging.getLogger(__name__)


def load_server(context, instance_id, server_id):
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
            if utils.bool_from_string(volume_support):
                volumes_info = client.volumes.get_server_volumes(server_id)
                volume_ids = [attachments.volumeId for attachments in
                              volumes_info]
                for volume_id in volume_ids:
                    volume_info = volume_client.volumes.get(volume_id)
                    volume = {'id': volume_info.id,
                              'size': volume_info.size}
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
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"


# If the compute server is in any of these states we can't perform any
# actions (delete, resize, etc).
SERVER_INVALID_ACTION_STATUSES = ["BUILD", "REBOOT", "REBUILD"]

# Statuses in which an instance can have an action performed.
VALID_ACTION_STATUSES = ["ACTIVE"]


class Instance(object):

    _data_fields = ['name', 'status', 'id', 'created', 'updated',
                    'flavor', 'links', 'addresses', 'volume']

    def __init__(self, context, db_info, server, service_status, volumes):
        self.context = context
        self.db_info = db_info
        self.server = server
        self.service_status = service_status
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
        server, volumes = load_server(context, db_info.id,
                                      db_info.compute_instance_id)
        task_status = db_info.task_status
        service_status = InstanceServiceStatus.find_by(instance_id=id)
        LOG.info("service status=%s" % service_status)
        return Instance(context, db_info, server, service_status, volumes)

    def delete(self, force=False):
        if not force and self.server.status in SERVER_INVALID_ACTION_STATUSES:
            raise rd_exceptions.UnprocessableEntity("Instance %s is not ready."
                                                    % self.id)
        LOG.debug(_("  ... deleting compute id = %s") %
                  self.server.id)
        self._delete_server()
        LOG.debug(_(" ... setting status to DELETING."))
        self.db_info.task_status = InstanceTasks.DELETING
        self.db_info.save()
        #TODO(tim.simpson): Put this in the task manager somehow to shepard
        #                   deletion?

    def _delete_server(self):
        try:
            self.server.delete()
        except nova_exceptions.NotFound, e:
            raise rd_exceptions.NotFound(uuid=self.id)
        except nova_exceptions.ClientException, e:
            raise rd_exceptions.ReddwarfError()

    @classmethod
    def _create_volume(cls, context, db_info, volume_size):
        volume_support = config.Config.get("reddwarf_volume_support", 'False')
        LOG.debug(_("Volume support = %s") % volume_support)
        if utils.bool_from_string(volume_support):
            LOG.debug(_("Starting to create the volume for the instance"))
            volume_client = create_nova_volume_client(context)
            volume_desc = ("mysql volume for %s" % context.tenant)
            volume_ref = volume_client.volumes.create(
                                        volume_size,
                                        display_name="mysql-%s" % db_info.id,
                                        display_description=volume_desc)
            #TODO(cp16net) this is bad to wait here for the volume create
            # before returning but this was a quick way to get it working
            # for now we need this to go into the task manager
            v_ref = volume_client.volumes.get(volume_ref.id)
            while not v_ref.status in ['available', 'error']:
                LOG.debug(_("waiting for volume [volume.status=%s]") %
                            v_ref.status)
                greenthread.sleep(1)
                v_ref = volume_client.volumes.get(volume_ref.id)

            if v_ref.status in ['error']:
                raise rd_exceptions.ReddwarfError(
                                    _("Could not create volume"))
            LOG.debug(_("Created volume %s") % v_ref)
            # The mapping is in the format:
            # <id>:[<type>]:[<size(GB)>]:[<delete_on_terminate>]
            # setting the delete_on_terminate instance to true=1
            mapping = "%s:%s:%s:%s" % (v_ref.id, '', v_ref.size, 1)
            # TODO(rnirmal) This mapping device needs to be configurable.
            # and we may have to do a little more trickery here.
            # We don't know what's the next device available on the
            # guest. Also in cases for ovz where this is mounted on
            # the host, that's not going to work for us.
            block_device = {'vdb': mapping}
            volume = [{'id': v_ref.id,
                       'size': v_ref.size}]
            LOG.debug("block_device = %s" % block_device)
            LOG.debug("volume = %s" % volume)

            device_path = CONFIG.get('device_path')
            mount_point = CONFIG.get('mount_point')
            LOG.debug(_("device_path = %s") % device_path)
            LOG.debug(_("mount_point = %s") % mount_point)
        else:
            LOG.debug(_("Skipping setting up the volume"))
            block_device = None
            device_path = None
            mount_point = None
            volume = None
            #end volume_support
        volume_info = {'block_device': block_device,
                       'device_path': device_path,
                       'mount_point': mount_point}
        return volume, volume_info

    @classmethod
    def create(cls, context, name, flavor_ref, image_id,
               databases, service_type, volume_size):
        db_info = DBInstance.create(name=name,
            task_status=InstanceTasks.NONE)
        LOG.debug(_("Created new Reddwarf instance %s...") % db_info.id)
        volume, volume_info = cls._create_volume(context,
                                                     db_info,
                                                     volume_size)
        client = create_nova_client(context)
        files = {"/etc/guest_info": "guest_id=%s\nservice_type=%s\n" %
                 (db_info.id, service_type)}
        server = client.servers.create(name, image_id, flavor_ref,
                     files=files,
                     block_device_mapping=volume_info['block_device'])
        LOG.debug(_("Created new compute instance %s.") % server.id)

        db_info.compute_instance_id = server.id
        db_info.save()
        service_status = InstanceServiceStatus.create(instance_id=db_info.id,
            status=ServiceStatuses.NEW)
        # Now wait for the response from the create to do additional work

        guest = create_guest_client(context, db_info.id)

        # populate the databases
        model_schemas = populate_databases(databases)
        guest.prepare(512, model_schemas, users=[],
                      device_path=volume_info['device_path'],
                      mount_point=volume_info['mount_point'])
        return Instance(context, db_info, server, service_status, volume)

    def get_guest(self):
        return create_guest_client(self.context, self.db_info.id)

    @property
    def id(self):
        return self.db_info.id

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
            return "REBOOT"
        # If the server is in any of these states they take precedence.
        if self.server.status in ["BUILD", "ERROR", "REBOOT", "RESIZE"]:
            return self.server.status
        # The service is only paused during a reboot.
        if ServiceStatuses.PAUSED == self.service_status.status:
            return "REBOOT"
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
    def created(self):
        return self.db_info.created

    @property
    def updated(self):
        return self.db_info.updated

    @property
    def flavor(self):
        return self.server.flavor

    @property
    def links(self):
        #TODO(tim.simpson): Review whether we should be returning the server
        # links.
        return self._build_links(self.server.links)

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
        LOG.info("Resizing flavor of instance %s..." % self.id)
        # TODO(tim.simpson): Validate the new flavor ID can be found or
        #                    raise FlavorNotFound exception.
        # TODO(tim.simpson): Actually perform flavor resize.
        raise RuntimeError("Not implemented (yet).")

    def resize_volume(self, new_size):
        LOG.info("Resizing volume of instance %s..." % self.id)
        # TODO(tim.simpson): Validate old_size < new_size, or raise
        #                    rd_exceptions.BadRequest.
        # TODO(tim.simpson): resize volume.
        raise RuntimeError("Not implemented (yet).")

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


class Instances(object):

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        client = create_nova_client(context)
        servers = client.servers.list()
        db_infos = DBInstance.find_all()
        ret = []
        find_server = create_server_list_matcher(servers)
        for db in db_infos:
            LOG.debug("checking for db [id=%s, compute_instance_id=%s]" %
                      (db.id, db.compute_instance_id))
            try:
                # TODO(hub-cap): Figure out if this is actually correct.
                # We are not sure if we should be doing some validation.
                # Basically if the server find returns nothing, but we
                # have something, there is a mismatch between what the
                # nova db has compared to what we have. We should have
                # a way to handle this.
                server = find_server(db.id, db.compute_instance_id)
                volumes = load_volumes(context, db.compute_instance_id)
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
        return ret


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


class DBInstance(DatabaseModelBase):
    """Defines the task being executed plus the start time."""

    #TODO(tim.simpson): Add start time.

    _data_fields = ['name', 'created', 'compute_instance_id',
                    'task_id', 'task_description', 'task_start_time']

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
        'root_enabled_history': RootHistory,
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


class RootHistory(ModelBase):

    _auto_generated_attrs = ['id']
    _data_fields = ['instance_id', 'user', 'created']
    _table_name = 'root_enabled_history'

    def __init__(self, instance_id, user):
        self.id = instance_id
        self.user = user
        self.created = utils.utcnow()

    def save(self):
        LOG.debug(_("Saving %s: %s") % (self.__class__.__name__, self.__dict__))
        return db.db_api.save(self)

    @classmethod
    def load(cls, context, instance_id):
        history = db.db_api.find_by(cls, id=instance_id)
        return history

    @classmethod
    def create(cls, context, instance_id, user):
        history = cls.load(context, instance_id)
        if history is not None:
            return history
        history = RootHistory(instance_id, user)
        history.save()
        return history


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
