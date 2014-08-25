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
from oslo_concurrency import processutils
from trove.cmd.common import with_initialize
from trove.common import profile


@with_initialize
def main(CONF):
    from trove.common import wsgi
    profile.setup_profiler('api', CONF.host)
    conf_file = CONF.find_file(CONF.api_paste_config)
    workers = CONF.trove_api_workers or processutils.get_worker_count()
    launcher = wsgi.launch('trove', CONF.bind_port, conf_file,
                           host=CONF.bind_host, workers=workers)
    launcher.wait()
