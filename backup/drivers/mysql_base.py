# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import os
import re
import shutil

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

from backup.drivers import base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MySQLBaseRunner(base.BaseRunner):
    def __init__(self, *args, **kwargs):
        self.datadir = kwargs.pop('db_datadir', '/var/lib/mysql/data')

        super(MySQLBaseRunner, self).__init__(*args, **kwargs)

    @property
    def user_and_pass(self):
        return ('--user=%(user)s --password=%(password)s --host=%(host)s' %
                {'user': CONF.db_user,
                 'password': CONF.db_password,
                 'host': CONF.db_host})

    @property
    def filename(self):
        return '%s.xbstream' % self.base_filename

    def check_process(self):
        """Check the backup output for 'completed OK!'."""
        LOG.debug('Checking backup process output.')
        with open(self.backup_log, 'r') as backup_log:
            output = backup_log.read()
            if not output:
                LOG.error("Backup log file %s empty.", self.backup_log)
                return False

            last_line = output.splitlines()[-1].strip()
            if not re.search('completed OK!', last_line):
                LOG.error(f"Backup did not complete successfully, last line:\n"
                          f"{last_line}")
                return False

        return True

    def get_metadata(self):
        LOG.debug('Getting metadata for backup %s', self.base_filename)
        meta = {}
        lsn = re.compile(r"The latest check point \(for incremental\): "
                         r"'(\d+)'")
        with open(self.backup_log, 'r') as backup_log:
            output = backup_log.read()
            match = lsn.search(output)
            if match:
                meta = {'lsn': match.group(1)}

        LOG.info("Updated metadata for backup %s: %s", self.base_filename,
                 meta)

        return meta

    def incremental_restore_cmd(self, incremental_dir):
        """Return a command for a restore with a incremental location."""
        args = {'restore_location': incremental_dir}
        return (self.decrypt_cmd + self.unzip_cmd + self.restore_cmd % args)

    def incremental_prepare_cmd(self, incremental_dir):
        if incremental_dir is not None:
            incremental_arg = '--incremental-dir=%s' % incremental_dir
        else:
            incremental_arg = ''

        args = {
            'restore_location': self.restore_location,
            'incremental_args': incremental_arg,
        }

        return self.incremental_prep % args

    def incremental_prepare(self, incremental_dir):
        prepare_cmd = self.incremental_prepare_cmd(incremental_dir)

        LOG.info("Running restore prepare command: %s.", prepare_cmd)
        processutils.execute(prepare_cmd, shell=True)

    def incremental_restore(self, location, checksum):
        """Recursively apply backups from all parents.

        If we are the parent then we restore to the restore_location and
        we apply the logs to the restore_location only.

        Otherwise if we are an incremental we restore to a subfolder to
        prevent stomping on the full restore data. Then we run apply log
        with the '--incremental-dir' flag

        :param location: The source backup location.
        :param checksum: Checksum of the source backup for validation.
        """
        metadata = self.storage.load_metadata(location, checksum)
        incremental_dir = None

        if 'parent_location' in metadata:
            LOG.info("Restoring parent: %(parent_location)s, "
                     "checksum: %(parent_checksum)s.", metadata)

            parent_location = metadata['parent_location']
            parent_checksum = metadata['parent_checksum']
            # Restore parents recursively so backup are applied sequentially
            self.incremental_restore(parent_location, parent_checksum)
            # for *this* backup set the incremental_dir
            # just use the checksum for the incremental path as it is
            # sufficiently unique /var/lib/mysql/<checksum>
            incremental_dir = os.path.join('/var/lib/mysql', checksum)
            os.makedirs(incremental_dir)
            command = self.incremental_restore_cmd(incremental_dir)
        else:
            # The parent (full backup) use the same command from InnobackupEx
            # super class and do not set an incremental_dir.
            LOG.info("Restoring back to full backup.")
            command = self.restore_command

        self.restore_content_length += self.unpack(location, checksum, command)
        self.incremental_prepare(incremental_dir)

        # Delete after restoring this part of backup
        if incremental_dir:
            shutil.rmtree(incremental_dir)
