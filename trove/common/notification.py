#    Copyright 2015 Tesora Inc.
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


import abc
import copy
import traceback

from oslo_log import log as logging
from oslo_utils import timeutils

from trove.common import cfg
from trove.common.exception import TroveError
from trove.common.i18n import _
from trove.conductor import api as conductor_api
from trove import rpc

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class EndNotification(object):

    @property
    def _notifier(self):
        '''
        Returns the notification for Trove API or TaskManager, otherwise
        returns an API to the conductor to whom to forward the notification
        '''
        return (self.context.notification
                if self.context.notification.server_type in ['api',
                                                             'taskmanager']
                else conductor_api.API(self.context))

    def __init__(self, context, **kwargs):
        self.context = context
        self.context.notification.payload.update(kwargs)

    def __enter__(self):
        return self.context.notification

    def __exit__(self, etype, value, tb):
        if etype:
            message = str(value)
            exception = traceback.format_exception(etype, value, tb)
            self._notifier.notify_exc_info(message, exception)
        else:
            self._notifier.notify_end()


class StartNotification(EndNotification):

    def __enter__(self):
        self.context.notification.notify_start()
        return super(StartNotification, self).__enter__()


class NotificationCastWrapper(object):

    def __init__(self, context, api):
        self.context = context
        self.api = api
        self.has_notification = hasattr(context, 'notification')

    def __enter__(self):
        if self.has_notification:
            self.old_server_type = self.context.notification.server_type
            self.context.notification.server_type = self.api

    def __exit__(self, etype, value, traceback):
        if self.has_notification:
            self.context.notification.server_type = self.old_server_type
            self.context.notification.needs_end_notification = False


class TroveBaseTraits(object):

    '''
    The base traits of all trove.* notifications.

    This class should correspond to trove_base_traits in
    ceilometer/event_definitions.yaml
    '''

    event_type_format = 'trove.instance.%s'

    def __init__(self, **kwargs):
        self.payload = {}

        instance = kwargs.pop('instance', None)
        if instance:
            self.instance = instance
            self.context = instance.context
            created_time = timeutils.isotime(instance.db_info.created)
            self.payload.update({
                'created_at': created_time,
                'name': instance.name,
                'instance_id': instance.id,
                'instance_name': instance.name,
                'instance_type_id': instance.flavor_id,
                'launched_at': created_time,
                'nova_instance_id': instance.server_id,
                'region': CONF.region,
                'state_description': instance.status.lower(),
                'state': instance.status.lower(),
                'tenant_id': instance.tenant_id,
                'user_id': instance.context.user,
            })

        self.payload.update(kwargs)

    def serialize(self, ctxt):

        if hasattr(self, 'instance'):
            if 'instance_type' not in self.payload:
                flavor_id = self.instance.flavor_id
                flavor = self.instance.nova_client.flavors.get(flavor_id)
                self.payload['instance_type'] = flavor.name
            self.payload['service_id'] = self.instance._get_service_id(
                self.instance.datastore_version.manager,
                CONF.notification_service_id)

        return self.payload

    def deserialize(self, ctxt, payload):
        self.payload = payload
        self.context = ctxt
        return self

    def notify(self, event_type, publisher_id=None):
        publisher_id = publisher_id or CONF.host
        event_type = self.event_type_format % event_type
        event_payload = self.serialize(self.context)
        LOG.debug('Sending event: %(event_type)s, %(payload)s' %
                  {'event_type': event_type, 'payload': event_payload})

        notifier = rpc.get_notifier(
            service='taskmanager', publisher_id=publisher_id)
        notifier.info(self.context, event_type, event_payload)


class TroveCommonTraits(TroveBaseTraits):

    '''
    Additional traits for trove.* notifications that describe
    instance action events

    This class should correspond to trove_common_traits in
    ceilometer/event_definitions.yaml
    '''

    def __init__(self, **kwargs):
        self.server = kwargs.pop('server', None)
        super(TroveCommonTraits, self).__init__(**kwargs)

    def serialize(self, ctxt):
        if hasattr(self, 'instance'):
            instance = self.instance
            if 'instance_type' not in self.payload:
                flavor = instance.nova_client.flavors.get(instance.flavor_id)
                self.payload['instance_size'] = flavor.ram
            if self.server is None:
                self.server = instance.nova_client.servers.get(
                    instance.server_id)
            self.payload['availability_zone'] = getattr(
                self.server, 'OS-EXT-AZ:availability_zone', None)
            if CONF.get(instance.datastore_version.manager).volume_support:
                self.payload.update({
                    'volume_size': instance.volume_size,
                    'nova_volume_id': instance.volume_id
                })

        return TroveBaseTraits.serialize(self, ctxt)


class TroveInstanceCreate(TroveCommonTraits):

    '''
    Additional traits for trove.instance.create notifications that describe
    instance action events

    This class should correspond to trove_instance_create in
    ceilometer/event_definitions.yaml
    '''

    def __init__(self, **kwargs):
        super(TroveInstanceCreate, self).__init__(**kwargs)

    def notify(self):
        super(TroveInstanceCreate, self).notify('create')


class TroveInstanceModifyVolume(TroveCommonTraits):

    '''
    Additional traits for trove.instance.create notifications that describe
    instance action events

    This class should correspond to trove_instance_modify_volume in
    ceilometer/event_definitions.yaml
    '''

    def __init__(self, **kwargs):
        super(TroveInstanceModifyVolume, self).__init__(**kwargs)

    def notify(self):
        super(TroveInstanceModifyVolume, self).notify('modify_volume')


class TroveInstanceModifyFlavor(TroveCommonTraits):

    '''
    Additional traits for trove.instance.create notifications that describe
    instance action events

    This class should correspond to trove_instance_modify_flavor in
    ceilometer/event_definitions.yaml
    '''

    def __init__(self, **kwargs):
        super(TroveInstanceModifyFlavor, self).__init__(**kwargs)

    def notify(self):
        super(TroveInstanceModifyFlavor, self).notify('modify_flavor')


class TroveInstanceDelete(TroveCommonTraits):

    '''
    Additional traits for trove.instance.create notifications that describe
    instance action events

    This class should correspond to trove_instance_delete in
    ceilometer/event_definitions.yaml
    '''

    def __init__(self, **kwargs):
        super(TroveInstanceDelete, self).__init__(**kwargs)

    def notify(self):
        super(TroveInstanceDelete, self).notify('delete')


class DBaaSQuotas(object):

    '''
    The traits of dbaas.quotas notifications.

    This class should correspond to dbaas.quotas in
    ceilometer/event_definitions.yaml
    '''

    event_type = 'dbaas.quota'

    def __init__(self, context, quota, usage):
        self.context = context

        self.payload = {
            'resource': quota.resource,
            'in_use': usage.in_use,
            'reserved': usage.reserved,
            'limit': quota.hard_limit,
            'updated': usage.updated
        }

    def notify(self):
        LOG.debug('Sending event: %(event_type)s, %(payload)s' %
                  {'event_type': DBaaSQuotas.event_type,
                   'payload': self.payload})

        notifier = rpc.get_notifier(
            service='taskmanager', publisher_id=CONF.host)

        notifier.info(self.context, DBaaSQuotas.event_type, self.payload)


class DBaaSAPINotification(object):

    '''
    The traits of dbaas.* notifications (except quotas).

    This class should correspond to dbaas_base_traits in
    ceilometer/event_definitions.yaml
    '''

    event_type_format = 'dbaas.%s.%s'
    notify_callback = None

    @classmethod
    def register_notify_callback(cls, callback):
        """A callback registered here will be fired whenever
        a notification is sent out. The callback should
        take a notification object, and event_qualifier.
        """
        cls.notify_callback = callback

    @abc.abstractmethod
    def event_type(self):
        'Returns the event type (like "create" for dbaas.create.start)'
        pass

    @abc.abstractmethod
    def required_start_traits(self):
        'Returns list of required traits for start notification'
        pass

    def optional_start_traits(self):
        'Returns list of optional traits for start notification'
        return []

    def required_end_traits(self):
        'Returns list of required traits for end notification'
        return []

    def optional_end_traits(self):
        'Returns list of optional traits for end notification'
        return []

    def required_error_traits(self):
        'Returns list of required traits for error notification'
        return ['message', 'exception']

    def optional_error_traits(self):
        'Returns list of optional traits for error notification'
        return ['instance_id']

    def required_base_traits(self):
        return ['tenant_id', 'client_ip', 'server_ip', 'server_type',
                'request_id']

    @property
    def server_type(self):
        return self.payload['server_type']

    @server_type.setter
    def server_type(self, server_type):
        self.payload['server_type'] = server_type

    @property
    def request_id(self):
        return self.payload['request_id']

    def __init__(self, context, **kwargs):
        self.context = context
        self.needs_end_notification = True

        self.payload = {}

        if 'request' in kwargs:
            request = kwargs.pop('request')
            self.payload.update({
                                'request_id': context.request_id,
                                'server_type': 'api',
                                'client_ip': request.remote_addr,
                                'server_ip': request.host,
                                'tenant_id': context.tenant,
                                })
        elif 'request_id' not in kwargs:
            raise TroveError(_("Notification %s must include 'request'"
                             " property") % self.__class__.__name__)

        self.payload.update(kwargs)

    def serialize(self, context):
        return self.payload

    def validate(self, required_traits):
        required_keys = set(required_traits)
        provided_keys = set(self.payload.keys())
        if not required_keys.issubset(provided_keys):
            raise TroveError(_("The following required keys not defined for"
                               " notification %(name)s: %(keys)s")
                             % {'name': self.__class__.__name__,
                                'keys': list(required_keys - provided_keys)})
        if 'server_type' not in self.payload:
            raise TroveError(_("Notification %s must include a"
                             " 'server_type' for correct routing")
                             % self.__class__.__name__)

    def _notify(self, event_qualifier, required_traits, optional_traits,
                **kwargs):
        self.payload.update(kwargs)
        self.validate(self.required_base_traits() + required_traits)
        available_values = self.serialize(self.context)
        payload = {k: available_values[k]
                   for k in self.required_base_traits() + required_traits}
        for k in optional_traits:
            if k in available_values:
                payload[k] = available_values[k]

        qualified_event_type = (DBaaSAPINotification.event_type_format
                                % (self.event_type(), event_qualifier))
        LOG.debug('Sending event: %(event_type)s, %(payload)s' %
                  {'event_type': qualified_event_type, 'payload': payload})

        context = copy.copy(self.context)
        del context.notification
        notifier = rpc.get_notifier(service=self.payload['server_type'])
        notifier.info(context, qualified_event_type, self.payload)
        if self.notify_callback:
            self.notify_callback(event_qualifier)

    def notify_start(self, **kwargs):
        self._notify('start', self.required_start_traits(),
                     self.optional_start_traits(), **kwargs)

    def notify_end(self, **kwargs):
        if self.needs_end_notification:
            self._notify('end', self.required_end_traits(),
                         self.optional_end_traits(), **kwargs)

    def notify_exc_info(self, message, exception):
        self.payload.update({
            'message': message,
            'exception': exception
        })
        self._notify('error', self.required_error_traits(),
                     self.optional_error_traits())


class DBaaSInstanceCreate(DBaaSAPINotification):

    def event_type(self):
        return 'instance_create'

    def required_start_traits(self):
        return ['name', 'flavor_id', 'datastore', 'datastore_version',
                'image_id', 'availability_zone']

    def optional_start_traits(self):
        return ['databases', 'users', 'volume_size', 'restore_point',
                'replica_of', 'replica_count', 'cluster_id', 'backup_id',
                'nics']

    def required_end_traits(self):
        return ['instance_id']


class DBaaSInstanceRestart(DBaaSAPINotification):

    def event_type(self):
        return 'instance_restart'

    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceResizeVolume(DBaaSAPINotification):

    def event_type(self):
        return 'instance_resize_volume'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'new_size']


class DBaaSInstanceResizeInstance(DBaaSAPINotification):

    def event_type(self):
        return 'instance_resize_instance'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'new_flavor_id']


class DBaaSInstancePromote(DBaaSAPINotification):

    def event_type(self):
        return 'instance_promote'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceEject(DBaaSAPINotification):

    def event_type(self):
        return 'instance_eject'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceDelete(DBaaSAPINotification):

    def event_type(self):
        return 'instance_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceResetStatus(DBaaSAPINotification):

    def event_type(self):
        return 'instance_reset_status'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceDetach(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'instance_detach'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSInstanceAttachConfiguration(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'instance_attach_configuration'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'configuration_id']


class DBaaSInstanceDetachConfiguration(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'instance_detach_configuration'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id']


class DBaaSClusterCreate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['name', 'datastore', 'datastore_version']

    @abc.abstractmethod
    def required_end_traits(self):
        return ['cluster_id']


class DBaaSClusterUpgrade(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_upgrade'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id', 'datastore_version']


class DBaaSClusterDelete(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id']


class DBaaSClusterResetStatus(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_reset_status'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id']


class DBaaSClusterAddShard(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_add_shard'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id']


class DBaaSClusterGrow(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_grow'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id']


class DBaaSClusterShrink(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'cluster_shrink'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['cluster_id']


class DBaaSBackupCreate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'backup_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['name', 'instance_id', 'description', 'parent_id']

    @abc.abstractmethod
    def required_end_traits(self):
        return ['backup_id']


class DBaaSBackupDelete(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'backup_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['backup_id']


class DBaaSDatabaseCreate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'database_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'dbname']


class DBaaSDatabaseDelete(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'database_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'dbname']


class DBaaSUserCreate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username']


class DBaaSUserDelete(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username']


class DBaaSUserUpdateAttributes(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_update_attributes'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username']


class DBaaSUserGrant(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_grant'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username', 'database']


class DBaaSUserRevoke(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_revoke'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username', 'database']


class DBaaSUserChangePassword(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'user_change_password'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'username']


class DBaaSConfigurationCreate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'configuration_create'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['name', 'datastore', 'datastore_version']

    def required_end_traits(self):
        return ['configuration_id']


class DBaaSConfigurationDelete(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'configuration_delete'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['configuration_id']


class DBaaSConfigurationUpdate(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'configuration_update'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['configuration_id', 'name', 'description']


class DBaaSConfigurationEdit(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'configuration_edit'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['configuration_id']


class DBaaSInstanceUpgrade(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'upgrade'

    @abc.abstractmethod
    def required_start_traits(self):
        return ['instance_id', 'datastore_version_id']
