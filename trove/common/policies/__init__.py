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

import itertools

from trove.common.policies import backups
from trove.common.policies import base
from trove.common.policies import clusters
from trove.common.policies import configuration_parameters
from trove.common.policies import configurations
from trove.common.policies import databases
from trove.common.policies import datastores
from trove.common.policies import flavors
from trove.common.policies import instances
from trove.common.policies import limits
from trove.common.policies import modules
from trove.common.policies import root
from trove.common.policies import user_access
from trove.common.policies import users


def list_rules():
    return itertools.chain(
        base.list_rules(),
        instances.list_rules(),
        root.list_rules(),
        users.list_rules(),
        user_access.list_rules(),
        databases.list_rules(),
        clusters.list_rules(),
        backups.list_rules(),
        configurations.list_rules(),
        configuration_parameters.list_rules(),
        datastores.list_rules(),
        flavors.list_rules(),
        limits.list_rules(),
        modules.list_rules()
    )
