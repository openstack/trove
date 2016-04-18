# Copyright 2016 Tesora, Inc.
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
#

from datetime import date

from oslo_log import log as logging

from trove.common import cfg
from trove.common.i18n import _
from trove.common import stream_codecs
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.module.drivers import module_driver


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


NR_ADD_LICENSE_CMD = ['nrsysmond-config', '--set', 'license_key=%s']
NR_SRV_CONTROL_CMD = ['/etc/init.d/newrelic-sysmond']


class NewRelicLicenseDriver(module_driver.ModuleDriver):
    """Module to set up the license for the NewRelic service."""

    def get_description(self):
        return "New Relic License Module Driver"

    def get_updated(self):
        return date(2016, 4, 12)

    @module_driver.output(
        log_message=_('Installing New Relic license key'),
        success_message=_('New Relic license key installed'),
        fail_message=_('New Relic license key not installed'))
    def apply(self, name, datastore, ds_version, data_file, admin_module):
        license_key = None
        data = operating_system.read_file(
            data_file, codec=stream_codecs.KeyValueCodec())
        for key, value in data.items():
            if 'license_key' == key.lower():
                license_key = value
                break
        if license_key:
            self._add_license_key(license_key)
            self._server_control('start')
        else:
            return False, "'license_key' not found in contents file"

    def _add_license_key(self, license_key):
        try:
            exec_args = {'timeout': 10,
                         'run_as_root': True,
                         'root_helper': 'sudo'}
            cmd = list(NR_ADD_LICENSE_CMD)
            cmd[-1] = cmd[-1] % license_key
            utils.execute_with_timeout(*cmd, **exec_args)
        except Exception:
            LOG.exception(_("Could not install license key '%s'") %
                          license_key)
            raise

    def _server_control(self, command):
        try:
            exec_args = {'timeout': 10,
                         'run_as_root': True,
                         'root_helper': 'sudo'}
            cmd = list(NR_SRV_CONTROL_CMD)
            cmd.append(command)
            utils.execute_with_timeout(*cmd, **exec_args)
        except Exception:
            LOG.exception(_("Could not %s New Relic server") % command)
            raise

    @module_driver.output(
        log_message=_('Removing New Relic license key'),
        success_message=_('New Relic license key removed'),
        fail_message=_('New Relic license key not removed'))
    def remove(self, name, datastore, ds_version, data_file):
        self._add_license_key("bad_key_that_is_exactly_40_characters_xx")
        self._server_control('stop')
