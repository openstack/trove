# Copyright 2011 OpenStack LLC.
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

from proboscis import test

from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.instances.delete"


@test(groups=[GROUP])
def delete_all():
    """Delete every single one."""
    user = CONFIG.users.find_user(Requirements(is_admin=False))
    dbaas = create_dbaas_client(user)
    instances = dbaas.instances.list()
    for instance in instances:
        instance.delete()
