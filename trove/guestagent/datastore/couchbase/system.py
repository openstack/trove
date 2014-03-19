# Copyright (c) 2013 eBay Software Foundation
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
from trove.common import cfg
CONF = cfg.CONF

TIME_OUT = 1200
COUCHBASE_CONF_DIR = '/etc/couchbase'
SERVICE_CANDIDATES = ["couchbase-server"]
cmd_couchbase_status = ('sudo /opt/couchbase/bin/couchbase-cli server-info '
                        '-c %(IP)s:8091 -u root -p %(PWD)s')
cmd_node_init = ('sudo /opt/couchbase/bin/couchbase-cli node-init '
                 '-c %(IP)s:8091 --node-init-data-path=%(data_path)s '
                 '-u root -p %(PWD)s')
cmd_cluster_init = ('sudo /opt/couchbase/bin/couchbase-cli cluster-init '
                    '-c %(IP)s:8091 --cluster-init-username=root '
                    '--cluster-init-password=%(PWD)s '
                    '--cluster-init-port=8091')
cmd_kill = 'sudo pkill -u couchbase'
cmd_own_data_dir = ('sudo chown couchbase:couchbase %s' %
                    CONF.get('couchbase').mount_point)
cmd_rm_old_data_dir = 'sudo rm -rf /opt/couchbase/var/lib/couchbase/data'
""" For optimal couchbase operations, swappiness of vm should be set to 0.
Reference link: http://docs.couchbase.com/couchbase-manual-2
.5/cb-admin/#using-couchbase-in-the-cloud """
cmd_set_swappiness = 'sudo sysctl vm.swappiness=0'
cmd_update_sysctl_conf = ('echo "vm.swappiness = 0" | sudo tee -a '
                          '/etc/sysctl.conf')
cmd_reset_pwd = 'sudo /opt/couchbase/bin/cbreset_password %(IP)s:8091'
pwd_file = COUCHBASE_CONF_DIR + '/secret_key'
