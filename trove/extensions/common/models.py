# Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from trove.common import cfg
from trove.common import exception
from trove.common.remote import create_guest_client
from trove.common import utils
from trove.db import get_db_api
from trove.guestagent.db import models as guest_models
from trove.instance import models as base_models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def load_and_verify(context, instance_id):
    # Load InstanceServiceStatus to verify if its running
    instance = base_models.Instance.load(context, instance_id)
    if not instance.is_datastore_running:
        raise exception.UnprocessableEntity(
            "Instance %s is not ready." % instance.id)
    else:
        return instance


class Root(object):

    @classmethod
    def load(cls, context, instance_id):
        load_and_verify(context, instance_id)
        # TODO(pdmars): remove the is_root_enabled call from the guest agent,
        # just check the database for this information.
        # If the root history returns null or raises an exception, the root
        # user hasn't been enabled.
        try:
            root_history = RootHistory.load(context, instance_id)
        except exception.NotFound:
            return False
        if not root_history:
            return False
        return True

    @classmethod
    def create(cls, context, instance_id, user, root_password,
               cluster_instances_list=None):
        load_and_verify(context, instance_id)
        if root_password:
            root = create_guest_client(context,
                                       instance_id).enable_root_with_password(
                root_password)
        else:
            root = create_guest_client(context, instance_id).enable_root()

        root_user = guest_models.RootUser()
        root_user.deserialize(root)

        # if cluster_instances_list none, then root create is called for
        # single instance, adding an RootHistory entry for the instance_id
        if cluster_instances_list is None:
            RootHistory.create(context, instance_id, user)

        return root_user

    @classmethod
    def delete(cls, context, instance_id):
        load_and_verify(context, instance_id)
        create_guest_client(context, instance_id).disable_root()


class ClusterRoot(Root):

    @classmethod
    def create(cls, context, instance_id, user, root_password,
               cluster_instances_list=None):
        root_user = super(ClusterRoot, cls).create(context, instance_id,
                                                   user, root_password,
                                                   cluster_instances_list=None)

        if cluster_instances_list:
            for instance in cluster_instances_list:
                RootHistory.create(context, instance, user)

        return root_user


class RootHistory(object):

    _auto_generated_attrs = ['id']
    _data_fields = ['instance_id', 'user', 'created']
    _table_name = 'root_enabled_history'

    def __init__(self, instance_id, user):
        self.id = instance_id
        self.user = user
        self.created = utils.utcnow()

    def save(self):
        LOG.debug("Saving %(name)s: %(dict)s" %
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
        return get_db_api().save(self)

    @classmethod
    def load(cls, context, instance_id):
        history = get_db_api().find_by(cls, id=instance_id)
        return history

    @classmethod
    def create(cls, context, instance_id, user):
        history = cls.load(context, instance_id)
        if history is not None:
            return history
        history = RootHistory(instance_id, user)
        return history.save()
