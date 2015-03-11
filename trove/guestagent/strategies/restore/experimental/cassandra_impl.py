#    Copyright 2014 Mirantis Inc.
#    All Rights Reserved.
#    Copyright 2015 Tesora Inc.
#    All Rights Reserved.
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

from oslo_log import log as logging

from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.cassandra import service
from trove.guestagent.strategies.restore import base

LOG = logging.getLogger(__name__)


class NodetoolSnapshot(base.RestoreRunner):
    """Implementation of restore using the Nodetool (http://goo.gl/QtXVsM)
    utility.
    """

    __strategy_name__ = 'nodetoolsnapshot'

    def __init__(self, storage, **kwargs):
        self._app = service.CassandraApp()
        kwargs.update({'restore_location': self._app.cassandra_data_dir})
        super(NodetoolSnapshot, self).__init__(storage, **kwargs)

    def pre_restore(self):
        """Prepare the data directory for restored files.
        The directory itself is not included in the backup archive
        (i.e. the archive is rooted inside the data directory).
        This is to make sure we can always restore an old backup
        even if the standard guest agent data directory changes.
        """

        LOG.debug('Initializing a data directory.')
        operating_system.create_directory(
            self.restore_location,
            user=self._app.cassandra_owner, group=self._app.cassandra_owner,
            force=True, as_root=True)

    def post_restore(self):
        """Updated ownership on the restored files.
        """

        LOG.debug('Updating ownership of the restored files.')
        operating_system.chown(
            self.restore_location,
            self._app.cassandra_owner, self._app.cassandra_owner,
            recursive=True, force=True, as_root=True)

    @property
    def base_restore_cmd(self):
        """Command to extract a backup archive into a given location.
        Attempt to preserve access modifiers on the archived files.
        """

        return 'sudo tar -xpPf - -C "%(restore_location)s"'
