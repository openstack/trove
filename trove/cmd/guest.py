# Copyright 2011 OpenStack Foundation
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
import sys

from oslo_config import cfg as openstack_cfg
from oslo_log import log as logging
from oslo_service import service as openstack_service

from trove.common import cfg
from trove.common import debug_utils
from trove.common.i18n import _
from trove.guestagent import api as guest_api
from trove.guestagent.common import operating_system

CONF = cfg.CONF
# The guest_id opt definition must match the one in common/cfg.py
CONF.register_opts([openstack_cfg.StrOpt('guest_id', default=None,
                                         help="ID of the Guest Instance."),
                    openstack_cfg.StrOpt('instance_rpc_encr_key',
                                         help=('Key (OpenSSL aes_cbc) for '
                                               'instance RPC encryption.'))])
LOG = logging.getLogger(__name__)


def main():
    log_levels = [
        'docker=WARN',
    ]
    default_log_levels = logging.get_default_log_levels()
    default_log_levels.extend(log_levels)
    logging.set_defaults(default_log_levels=default_log_levels)
    logging.register_options(CONF)

    cfg.parse_args(sys.argv)
    logging.setup(CONF, None)
    debug_utils.setup()

    from trove.guestagent import dbaas
    manager = dbaas.datastore_registry().get(CONF.datastore_manager)
    if not manager:
        msg = (_("Manager class not registered for datastore manager %s") %
               CONF.datastore_manager)
        raise RuntimeError(msg)

    if not CONF.guest_id:
        msg = (_("The guest_id parameter is not set. guest_info.conf "
               "was not injected into the guest or not read by guestagent"))
        raise RuntimeError(msg)

    # Create user and group for running docker container.
    LOG.info('Creating user and group for database service')
    uid = cfg.get_configuration_property('database_service_uid')
    operating_system.create_user('database', uid)

    # rpc module must be loaded after decision about thread monkeypatching
    # because if thread module is not monkeypatched we can't use eventlet
    # executor from oslo_messaging library.
    from trove import rpc
    rpc.init(CONF)

    from trove.common.rpc import service as rpc_service
    server = rpc_service.RpcService(
        key=CONF.instance_rpc_encr_key,
        topic="guestagent.%s" % CONF.guest_id,
        manager=manager, host=CONF.guest_id,
        rpc_api_version=guest_api.API.API_LATEST_VERSION)

    launcher = openstack_service.launch(CONF, server, restart_method='mutate')
    launcher.wait()
