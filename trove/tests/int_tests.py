# Copyright 2014 OpenStack Foundation
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

import proboscis
from trove.tests.api import backups
from trove.tests.api import configurations
from trove.tests.api import databases
from trove.tests.api import datastores
from trove.tests.api import flavors
from trove.tests.api import instances
from trove.tests.api import instances_actions
from trove.tests.api.mgmt import accounts
from trove.tests.api.mgmt import admin_required
from trove.tests.api.mgmt import hosts
from trove.tests.api.mgmt import instances as mgmt_instances
from trove.tests.api.mgmt import storage
from trove.tests.api import replication
from trove.tests.api import root
from trove.tests.api import user_access
from trove.tests.api import users
from trove.tests.api import versions


GROUP_SERVICES_INITIALIZE = "services.initialize"


black_box_groups = [
    flavors.GROUP,
    users.GROUP,
    user_access.GROUP,
    databases.GROUP,
    root.GROUP,
    GROUP_SERVICES_INITIALIZE,
    instances.GROUP_START,
    instances.GROUP_QUOTAS,
    instances.GROUP_SECURITY_GROUPS,
    backups.GROUP,
    replication.GROUP,
    configurations.GROUP,
    datastores.GROUP,
    instances_actions.GROUP_RESIZE,
    # TODO(SlickNik): The restart tests fail intermittently so pulling
    # them out of the blackbox group temporarily. Refer to Trove bug:
    # https://bugs.launchpad.net/trove/+bug/1204233
    # instances_actions.GROUP_RESTART,
    instances_actions.GROUP_STOP_MYSQL,
    instances.GROUP_STOP,
    versions.GROUP,
    instances.GROUP_GUEST,
]
proboscis.register(groups=["blackbox", "mysql"],
                   depends_on_groups=black_box_groups)

simple_black_box_groups = [
    GROUP_SERVICES_INITIALIZE,
    flavors.GROUP,
    versions.GROUP,
    instances.GROUP_START_SIMPLE,
    admin_required.GROUP,
]
proboscis.register(groups=["simple_blackbox"],
                   depends_on_groups=simple_black_box_groups)

black_box_mgmt_groups = [
    accounts.GROUP,
    hosts.GROUP,
    storage.GROUP,
    instances_actions.GROUP_REBOOT,
    admin_required.GROUP,
    mgmt_instances.GROUP,
]
proboscis.register(groups=["blackbox_mgmt"],
                   depends_on_groups=black_box_mgmt_groups)

# Datastores groups for int-tests
datastore_group = [
    GROUP_SERVICES_INITIALIZE,
    flavors.GROUP,
    versions.GROUP,
    instances.GROUP_START_SIMPLE,
]
proboscis.register(groups=["cassandra", "couchbase", "mongodb", "postgresql",
                           "redis"],
                   depends_on_groups=datastore_group)
