#Copyright 2014 OpenStack Foundation

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from trove.db import get_db_api
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def persisted_models():
    return {'conductor_lastseen': LastSeen}


class LastSeen(object):
    """A table used only by Conductor to discard messages that arrive
       late and out of order.
    """
    _auto_generated_attrs = []
    _data_fields = ['instance_id', 'method_name', 'sent']
    _table_name = 'conductor_lastseen'
    preserve_on_delete = False

    def __init__(self, instance_id, method_name, sent):
        self.instance_id = instance_id
        self.method_name = method_name
        self.sent = sent

    def save(self):
        return get_db_api().save(self)

    @classmethod
    def load(cls, instance_id, method_name):
        seen = get_db_api().find_by(cls,
                                    instance_id=instance_id,
                                    method_name=method_name)
        return seen

    @classmethod
    def create(cls, instance_id, method_name, sent):
        seen = LastSeen(instance_id, method_name, sent)
        return seen.save()
