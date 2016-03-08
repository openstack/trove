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
from trove.guestagent.common import operating_system
from trove.guestagent.module.drivers import module_driver


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PingDriver(module_driver.ModuleDriver):
    """Concrete module to show implementation and functionality. Responds
    like an actual module driver, but does nothing except return the
    value of the message key in the contents file.  For example, if the file
    contains 'message=Hello' then the message returned by module-apply will
    be 'Hello.'
    """

    def get_type(self):
        return 'ping'

    def get_description(self):
        return "Ping Guestagent Module Driver"

    def get_updated(self):
        return date(2016, 3, 4)

    def apply(self, name, datastore, ds_version, data_file):
        success = False
        message = "Message not found in contents file"
        try:
            data = operating_system.read_file(
                data_file, codec=stream_codecs.KeyValueCodec())
            for key, value in data.items():
                if 'message' == key.lower():
                    success = True
                    message = value
                    break
        except Exception:
            # assume we couldn't read the file, because there was some
            # issue with it (for example, it's a binary file). Just log
            # it and drive on.
            LOG.error(_("Could not extract contents from '%s' - possibly "
                      "a binary file?") % name)

        return success, message

    def _is_binary(self, data_str):
        bool(data_str.translate(None, self.TEXT_CHARS))

    def remove(self, name, datastore, ds_version, data_file):
        return True, ""
