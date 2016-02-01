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
from trove.tests.api.mgmt import datastore_versions
from trove.tests.api.mgmt import hosts
from trove.tests.api.mgmt import instances as mgmt_instances
from trove.tests.api.mgmt import storage
from trove.tests.api import replication
from trove.tests.api import root
from trove.tests.api import user_access
from trove.tests.api import users
from trove.tests.api import versions
from trove.tests.scenario.groups import backup_group
from trove.tests.scenario.groups import cluster_actions_group
from trove.tests.scenario.groups import configuration_group
from trove.tests.scenario.groups import database_actions_group
from trove.tests.scenario.groups import guest_log_group
from trove.tests.scenario.groups import instance_actions_group
from trove.tests.scenario.groups import instance_create_group
from trove.tests.scenario.groups import instance_delete_group
from trove.tests.scenario.groups import negative_cluster_actions_group
from trove.tests.scenario.groups import replication_group
from trove.tests.scenario.groups import user_actions_group


GROUP_SERVICES_INITIALIZE = "services.initialize"
GROUP_SETUP = 'dbaas.setup'


def build_group(*groups):
    def merge(collection, *items):
        for item in items:
            if isinstance(item, list):
                merge(collection, *item)
            else:
                if item not in collection:
                    collection.append(item)

    out = []
    merge(out, *groups)
    return out


def register(datastores, *test_groups):
    proboscis.register(groups=build_group(datastores),
                       depends_on_groups=build_group(*test_groups))

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
    datastore_versions.GROUP,
]
proboscis.register(groups=["blackbox", "mysql"],
                   depends_on_groups=black_box_groups)

simple_black_box_groups = [
    GROUP_SERVICES_INITIALIZE,
    flavors.GROUP,
    versions.GROUP,
    instances.GROUP_START_SIMPLE,
    admin_required.GROUP,
    datastore_versions.GROUP,
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
    datastore_versions.GROUP,
]
proboscis.register(groups=["blackbox_mgmt"],
                   depends_on_groups=black_box_mgmt_groups)

#
# Group designations for datastore agnostic int-tests
#
# Base groups for all other groups
base_groups = [
    GROUP_SERVICES_INITIALIZE,
    flavors.GROUP,
    versions.GROUP,
    GROUP_SETUP
]

# Cluster-based groups
cluster_actions_groups = list(base_groups)
cluster_actions_groups.extend([cluster_actions_group.GROUP,
                               negative_cluster_actions_group.GROUP])

# Single-instance based groups
instance_create_groups = list(base_groups)
instance_create_groups.extend([instance_create_group.GROUP,
                               instance_delete_group.GROUP])

backup_groups = list(instance_create_groups)
backup_groups.extend([backup_group.GROUP])

configuration_groups = list(instance_create_groups)
configuration_groups.extend([configuration_group.GROUP])

database_actions_groups = list(instance_create_groups)
database_actions_groups.extend([database_actions_group.GROUP])

guest_log_groups = list(instance_create_groups)
guest_log_groups.extend([guest_log_group.GROUP])

instance_actions_groups = list(instance_create_groups)
instance_actions_groups.extend([instance_actions_group.GROUP])

replication_groups = list(instance_create_groups)
replication_groups.extend([replication_group.GROUP])

user_actions_groups = list(instance_create_groups)
user_actions_groups.extend([user_actions_group.GROUP])

# groups common to all datastores
common_groups = list(instance_actions_groups)
common_groups.extend([guest_log_groups])

# Register: Module based groups
register(["backup"], backup_groups)
register(["cluster"], cluster_actions_groups)
register(["configuration"], configuration_groups)
register(["database"], database_actions_groups)
register(["guest_log"], guest_log_groups)
register(["instance", "instance_actions"], instance_actions_groups)
register(["instance_create"], instance_create_groups)
register(["replication"], replication_groups)
register(["user"], user_actions_groups)

# Register: Datastore based groups
# These should contain all functionality currently supported by the datastore
register(["db2_supported"], common_groups,
         database_actions_groups, user_actions_groups)
register(["cassandra_supported"], common_groups,
         backup_groups, configuration_groups)
register(["couchbase_supported"], common_groups, backup_groups)
register(["couchdb_supported"], common_groups)
register(["postgresql_supported"], common_groups,
         backup_groups, database_actions_groups, configuration_groups,
         user_actions_groups)
register(["mariadb_supported", "mysql_supported", "percona_supported"],
         common_groups,
         backup_groups, configuration_groups, database_actions_groups,
         replication_groups, user_actions_groups)
register(["mongodb_supported"], common_groups,
         backup_groups, cluster_actions_groups, configuration_groups,
         database_actions_groups, user_actions_groups)
register(["pxc_supported"], common_groups,
         cluster_actions_groups)
register(["redis_supported"], common_groups,
         backup_groups, replication_groups)
register(["vertica_supported"], common_groups,
         cluster_actions_groups)
