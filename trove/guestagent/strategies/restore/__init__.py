# Copyright 2013 Hewlett-Packard Development Company, L.P.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from trove.guestagent.strategy import Strategy
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def get_restore_strategy(restore_driver, ns=__name__):
    LOG.debug("Getting restore strategy: %s." % restore_driver)
    return Strategy.get_strategy(restore_driver, ns)
