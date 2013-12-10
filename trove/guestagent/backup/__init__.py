# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from trove.guestagent.backup.backupagent import BackupAgent

AGENT = BackupAgent()


def backup(context, backup_info):
    """
    Main entry point for starting a backup based on the given backup id.  This
    will create a backup for this DB instance and will then store the backup
    in a configured repository (e.g. Swift)

    :param context:     the context token which contains the users details
    :param backup_id:   the id of the persisted backup object
    """
    return AGENT.execute_backup(context, backup_info)


def restore(context, backup_info, restore_location):
    """
    Main entry point for restoring a backup based on the given backup id.  This
    will transfer backup data to this instance an will carry out the
    appropriate restore procedure (eg. mysqldump)

    :param context:     the context token which contains the users details
    :param backup_id:   the id of the persisted backup object
    """
    return AGENT.execute_restore(context, backup_info, restore_location)
