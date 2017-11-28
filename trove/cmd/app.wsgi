# Copyright 2017 Amrith Kumar.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""
Used for deploying Trove API through mod-wsgi
"""

from oslo_log import log as logging
from trove.cmd.common import with_initialize
from trove.common import pastedeploy
from trove.common import profile

LOG = logging.getLogger('trove.cmd.app')


@with_initialize
def wsgimain(CONF):
    from trove.common import cfg
    from trove.common import notification
    from trove.instance import models as inst_models

    notification.DBaaSAPINotification.register_notify_callback(
        inst_models.persist_instance_fault)
    cfg.set_api_config_defaults()
    profile.setup_profiler('api', CONF.host)
    conf_file = CONF.find_file(CONF.api_paste_config)
    LOG.debug("Trove started on %s", CONF.host)
    return pastedeploy.paste_deploy_app(conf_file, 'trove', {})

application = wsgimain()
