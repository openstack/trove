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
from reddwarf.guestagent import api as guest_api
from reddwarf.common import exception as rd_exceptions
from reddwarf.common import utils
from reddwarf.instance.tasks import InstanceTask
from reddwarf.instance.tasks import InstanceTasks
from novaclient.v1_1.client import Client
from reddwarf.common.models import ModelBase
from novaclient import exceptions as nova_exceptions
from reddwarf.common.models import NovaRemoteModelBase
from reddwarf.common.remote import create_nova_client

CONFIG = config.Config
LOG = logging.getLogger(__name__)


def load_server(client, uuid):
    """Loads a server or raises an exception."""
    if uuid is None:
        raise TypeError("Argument uuid not defined.")
    try:
        server = client.servers.get(uuid)
    except nova_exceptions.NotFound, e:
        #TODO(cp16net) would this be the wrong id to show the user?
        raise rd_exceptions.NotFound(uuid=uuid)
    except nova_exceptions.ClientException, e:
        raise rd_exceptions.ReddwarfError(str(e))
    return server


class InstanceStatus(object):

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    BUILD = "BUILD"
    FAILED = "FAILED"
    SHUTDOWN = "SHUTDOWN"


# If the compute server is in any of these states we can't delete it.
SERVER_INVALID_DELETE_STATUSES = ["BUILD", "REBOOT", "REBUILD"]

# Statuses in which an instance can have an action performed.
VALID_ACTION_STATUSES = ["ACTIVE"]


class Instance(object):

    _data_fields = ['name', 'status', 'id', 'created', 'updated',
                    'flavor', 'links', 'addresses']

    def __init__(self, context, db_info, server, service_status):
        self.context = context
        self.db_info = db_info
        self.server = server
        self.service_status = service_status

    @staticmethod
    def load(context, uuid):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif uuid is None:
            raise TypeError("Argument uuid not defined.")
        client = create_nova_client(context)
        db_info = DBInstance.find_by(id=uuid)
        server = load_server(client,
                                      db_info.compute_instance_id)
        task_status = db_info.task_status
        service_status = InstanceServiceStatus.find_by(instance_id=uuid)
        return Instance(context, db_info, server, service_status)

    def delete(self, force=False):
        LOG.debug("Deleting instance %s..." % self.id)
        if not force and self.server.status in SERVER_INVALID_DELETE_STATUSES:
            raise rd_exceptions.UnprocessableEntity

        LOG.debug("  ... deleting compute id = %s" %
                  self.server.id)
        self._delete_server()
        LOG.debug(" ... setting status to DELETING.")
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
    def create(cls, context, name, flavor_ref, image_id):
        client = create_nova_client(context)
        server = client.servers.create(name, image_id, flavor_ref)
        LOG.debug("Created new compute instance %s." % server.id)
        db_info = DBInstance.create(name=name,
            compute_instance_id=server.id,
            task_status=InstanceTasks.BUILDING)
        LOG.debug("Created new Reddwarf instance %s..." % db_info.id)
        service_status = InstanceServiceStatus.create(instance_id=db_info.id,
            status=ServiceStatuses.NEW)
        # Now wait for the response from the create to do additional work
        guest_api.API().prepare(context, db_info.id, 512, [])
        return Instance(context, db_info, server, service_status)

    @property
    def id(self):
        return self.db_info.id

    @property
    def is_building(self):
        return self.status in [InstanceStatus.BUILD]

    @property
    def is_sql_running(self):
        """True if the service status indicates MySQL is up and running."""
        return service_status.status in MYSQL_RESPONSIVE_STATUSES

    @property
    def name(self):
        return self.server.name

    @property
    def status(self):
        #TODO(tim.simpson): As we enter more advanced cases dealing with
        # timeouts determine if the task_status should be integrated here
        # or removed entirely.
        # If the server is in any of these states they take precedence.
        if self.server.status in ["ERROR", "REBOOT", "RESIZE"]:
            return self.server.status
        # The service is only paused during a reboot.
        if ServiceStatuses.PAUSED == self.service_status.status:
            return "REBOOT"
        if ServiceStatuses.NEW == self.service_status.status:
            return "REBOOT"
        # If the service status is NEW, then we are building.
        if self.service_status.status == ServiceStatuses.NEW:
            return InstanceStatus.BUILD
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
                  "performed. Status [%s]" % self.status
            LOG.debug(msg)
            raise rd_exceptions.UnprocessableEntity(msg)


class Instances(object):

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        client = create_nova_client(context)
        servers = client.servers.list()
        db_infos = DBInstance.find_all()
        ret = []
        for db in db_infos:
            status = InstanceServiceStatus.find_by(instance_id=db.id)
            for server in servers:
                if server.id == db.compute_instance_id:
                    ret.append(Instance(context, db, server, status))
                    break
        return ret


class DatabaseModelBase(ModelBase):
    _auto_generated_attrs = ['id']

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        instance = cls(**values).save()
        if not instance.is_valid():
            raise InvalidModelError(instance.errors)
        return instance

    def save(self):
        if not self.is_valid():
            raise InvalidModelError(self.errors)
        self['updated_at'] = utils.utcnow()
        LOG.debug("Saving %s: %s" % (self.__class__.__name__, self.__dict__))
        return db.db_api.save(self)

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
