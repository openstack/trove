#Copyright [2013] Hewlett-Packard Development Company, L.P.

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

"""Model classes that form the core of snapshots functionality."""

from reddwarf.common import cfg
from reddwarf.common import exception
from reddwarf.db.models import DatabaseModelBase
from reddwarf.openstack.common import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
SWIFT_CONTAINER = CONF.backup_swift_container


class BackupState(object):
    NEW = "NEW"
    BUILDING = "BUILDING"
    SAVING = "SAVING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING_STATES = [NEW, BUILDING, SAVING]
    END_STATES = [COMPLETED, FAILED]


class Backup(object):

    @classmethod
    def create(cls, context, instance_id, name, description=None):
        """
        create db record for Backup
        :param cls:
        :param context: tenant_id included
        :param instance_id:
        :param name:
        :param note:
        :return:
        """
        try:
            db_info = DBBackup.create(name=name,
                                      description=description,
                                      tenant_id=context.tenant,
                                      state=BackupState.NEW,
                                      instance_id=instance_id,
                                      deleted=False)
            return db_info
        except exception.InvalidModelError as ex:
            LOG.exception("Unable to create Backup record:")
            raise exception.BackupCreationError(str(ex))

    @classmethod
    def running(cls, instance_id, exclude=None):
        """
        Returns the first running backup for instance_id
        :param instance_id: Id of the instance
        :param exclude: Backup ID to exclude from the query (any other running)
        """
        query = DBBackup.query()
        query = query.filter(DBBackup.instance_id == instance_id,
                             DBBackup.state.in_(BackupState.RUNNING_STATES))
        # filter out deleted backups, PEP8 does not like field == False!
        query = query.filter_by(deleted=False)
        if exclude:
            query = query.filter(DBBackup.id != exclude)
        return query.first()

    @classmethod
    def get_by_id(cls, backup_id, deleted=False):
        """
        get the backup for that id
        :param cls:
        :param backup_id: Id of the backup to return
        :param deleted: Return deleted backups
        :return:
        """
        try:
            db_info = DBBackup.find_by(id=backup_id, deleted=deleted)
            return db_info
        except exception.NotFound:
            raise exception.NotFound(uuid=backup_id)

    @classmethod
    def list(cls, context):
        """
        list all live Backups belong to given tenant
        :param cls:
        :param context: tenant_id included
        :return:
        """
        db_info = DBBackup.find_all(tenant_id=context.tenant,
                                    deleted=False)
        return db_info

    @classmethod
    def list_for_instance(cls, instance_id):
        """
        list all live Backups associated with given instance
        :param cls:
        :param instance_id:
        :return:
        """
        db_info = DBBackup.find_all(instance_id=instance_id,
                                    deleted=False)
        return db_info

    @classmethod
    def delete(cls, backup_id):
        """
        update Backup table on deleted flag for given Backup
        :param cls:
        :param backup_id: Backup uuid
        :return:
        """
        #TODO: api (service.py) might take care of actual deletion
        # on remote swift
        db_info = cls.get_by_id(backup_id)
        db_info.delete()


def persisted_models():
    return {'backups': DBBackup}


class DBBackup(DatabaseModelBase):
    """A table for Backup records"""
    _data_fields = ['id', 'name', 'description', 'location', 'backup_type',
                    'size', 'tenant_id', 'state', 'instance_id',
                    'checksum', 'backup_timestamp', 'deleted', 'created',
                    'updated', 'deleted_at']
    preserve_on_delete = True

    @property
    def is_running(self):
        return self.state in BackupState.RUNNING_STATES

    @property
    def is_done(self):
        return self.state in BackupState.END_STATES
