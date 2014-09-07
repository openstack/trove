#    Copyright 2012 OpenStack Foundation
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
import datetime

from trove.common import cfg
from trove.common import remote
from trove.common import utils
from trove.openstack.common import log as logging
from trove.instance import models as imodels
from trove.instance.models import load_instance, InstanceServiceStatus
from trove.instance import models as instance_models
from trove.extensions.mysql import models as mysql_models
from trove import rpc

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def load_mgmt_instances(context, deleted=None, client=None,
                        include_clustered=None):
    if not client:
        client = remote.create_nova_client(context)
    try:
        mgmt_servers = client.rdservers.list()
    except AttributeError:
        mgmt_servers = client.servers.list(search_opts={'all_tenants': 1})
    LOG.info("Found %d servers in Nova" %
             len(mgmt_servers if mgmt_servers else []))
    args = {}
    if deleted is not None:
        args['deleted'] = deleted
    if not include_clustered:
        args['cluster_id'] = None
    db_infos = instance_models.DBInstance.find_all(**args)

    instances = MgmtInstances.load_status_from_existing(context, db_infos,
                                                        mgmt_servers)
    return instances


def load_mgmt_instance(cls, context, id):
    try:
        instance = load_instance(cls, context, id, needs_server=True)
        client = remote.create_nova_client(context)
        try:
            server = client.rdservers.get(instance.server_id)
        except AttributeError:
            server = client.servers.get(instance.server_id)
        if hasattr(server, 'host'):
            instance.server.host = server.host
        elif hasattr(server, 'hostId'):
            instance.server.host = server.hostId
        if hasattr(server, 'deleted'):
            instance.server.deleted = server.deleted
        if hasattr(server, 'deleted_at'):
            instance.server.deleted_at = server.deleted_at
        if hasattr(server, 'local_id'):
            instance.server.local_id = server.local_id
        assert instance.server is not None
    except Exception as e:
        LOG.error(e)
        instance = load_instance(cls, context, id, needs_server=False)
    return instance


class SimpleMgmtInstance(imodels.BaseInstance):
    def __init__(self, context, db_info, server, datastore_status):
        super(SimpleMgmtInstance, self).__init__(context, db_info, server,
                                                 datastore_status)

    @property
    def status(self):
        if self.deleted:
            return imodels.InstanceStatus.SHUTDOWN
        return super(SimpleMgmtInstance, self).status

    @property
    def deleted(self):
        return self.db_info.deleted

    @property
    def deleted_at(self):
        return self.db_info.deleted_at

    @classmethod
    def load(cls, context, id):
        return load_mgmt_instance(cls, context, id)

    @property
    def task_description(self):
        return self.db_info.task_description


class DetailedMgmtInstance(SimpleMgmtInstance):
    def __init__(self, *args, **kwargs):
        super(DetailedMgmtInstance, self).__init__(*args, **kwargs)
        self.volume = None
        self.volume_used = None
        self.volume_total = None
        self.root_history = None

    @classmethod
    def load(cls, context, id):
        instance = load_mgmt_instance(cls, context, id)
        client = remote.create_cinder_client(context)
        try:
            instance.volume = client.volumes.get(instance.volume_id)
        except Exception:
            instance.volume = None
            # Populate the volume_used attribute from the guest agent.
        instance_models.load_guest_info(instance, context, id)
        instance.root_history = mysql_models.RootHistory.load(context=context,
                                                              instance_id=id)
        return instance


class MgmtInstance(imodels.Instance):
    def get_diagnostics(self):
        return self.get_guest().get_diagnostics()

    def stop_db(self):
        return self.get_guest().stop_db()

    def get_hwinfo(self):
        return self.get_guest().get_hwinfo()


class MgmtInstances(imodels.Instances):
    @staticmethod
    def load_status_from_existing(context, db_infos, servers):
        def load_instance(context, db, status, server=None):
            return SimpleMgmtInstance(context, db, server, status)

        if context is None:
            raise TypeError("Argument context not defined.")
        find_server = imodels.create_server_list_matcher(servers)
        instances = imodels.Instances._load_servers_status(load_instance,
                                                           context,
                                                           db_infos,
                                                           find_server)
        _load_servers(instances, find_server)
        return instances


def _load_servers(instances, find_server):
    for instance in instances:
        db = instance.db_info
        instance.server = None
        try:
            server = find_server(db.id, db.compute_instance_id)
            instance.server = server
        except Exception as ex:
            LOG.error(ex)
    return instances


def publish_exist_events(transformer, admin_context):
    notifier = rpc.get_notifier("taskmanager")
    notifications = transformer()
    # clear out admin_context.auth_token so it does not get logged
    admin_context.auth_token = None
    for notification in notifications:
        notifier.info(admin_context, "trove.instance.exists", notification)


class NotificationTransformer(object):
    def __init__(self, **kwargs):
        pass

    @staticmethod
    def _get_audit_period():
        now = datetime.datetime.now()
        audit_start = utils.isotime(now, subsecond=True)
        audit_end = utils.isotime(
            now + datetime.timedelta(
                seconds=CONF.exists_notification_ticks * CONF.report_interval),
            subsecond=True)
        return audit_start, audit_end

    def _get_service_id(self, datastore_manager, id_map):
        if datastore_manager in id_map:
            datastore_manager_id = id_map[datastore_manager]
        else:
            datastore_manager_id = cfg.UNKNOWN_SERVICE_ID
            LOG.error("Datastore ID for Manager (%s) is not configured"
                      % datastore_manager)
        return datastore_manager_id

    def transform_instance(self, instance, audit_start, audit_end):
        payload = {
            'audit_period_beginning': audit_start,
            'audit_period_ending': audit_end,
            'created_at': instance.created,
            'display_name': instance.name,
            'instance_id': instance.id,
            'instance_name': instance.name,
            'instance_type_id': instance.flavor_id,
            'launched_at': instance.created,
            'nova_instance_id': instance.server_id,
            'region': CONF.region,
            'state_description': instance.status.lower(),
            'state': instance.status.lower(),
            'tenant_id': instance.tenant_id
        }
        payload['service_id'] = self._get_service_id(
            instance.datastore_version.manager, CONF.notification_service_id)
        return payload

    def __call__(self):
        audit_start, audit_end = NotificationTransformer._get_audit_period()
        messages = []
        db_infos = instance_models.DBInstance.find_all(deleted=False)
        for db_info in db_infos:
            service_status = InstanceServiceStatus.find_by(
                instance_id=db_info.id)
            instance = SimpleMgmtInstance(None, db_info, None, service_status)
            message = self.transform_instance(instance, audit_start, audit_end)
            messages.append(message)
        return messages


class NovaNotificationTransformer(NotificationTransformer):
    def __init__(self, **kwargs):
        super(NovaNotificationTransformer, self).__init__(**kwargs)
        self.context = kwargs['context']
        self.nova_client = remote.create_admin_nova_client(self.context)
        self._flavor_cache = {}

    def _lookup_flavor(self, flavor_id):
        if flavor_id in self._flavor_cache:
            LOG.debug("Flavor cache hit for %s" % flavor_id)
            return self._flavor_cache[flavor_id]
        # fetch flavor resource from nova
        LOG.info("Flavor cache miss for %s" % flavor_id)
        flavor = self.nova_client.flavors.get(flavor_id)
        self._flavor_cache[flavor_id] = flavor.name if flavor else 'unknown'
        return self._flavor_cache[flavor_id]

    def __call__(self):
        audit_start, audit_end = NotificationTransformer._get_audit_period()
        instances = load_mgmt_instances(self.context, deleted=False,
                                        client=self.nova_client)
        messages = []
        for instance in filter(
                lambda inst: inst.status != 'SHUTDOWN' and inst.server,
                instances):
            message = {
                'instance_type': self._lookup_flavor(instance.flavor_id),
                'user_id': instance.server.user_id
            }
            message.update(self.transform_instance(instance,
                                                   audit_start,
                                                   audit_end))
            messages.append(message)
        return messages
