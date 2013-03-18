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
from reddwarf.common import utils

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
    def delete(cls, id):
        """
        update Backup table on deleted flag for given Backup
        :param cls:
        :param id: Backup uuid
        :return:
        """
        #TODO: api (service.py) might take care of actual deletion
        # on remote swift
        try:
            db_info = DBBackup.find_by(id=id, deleted=False)
            db_info.update(deleted=True, deleted_at=utils.utcnow())
        except exception.ReddwarfError as ex:
            LOG.exception("Backup record cannot be updated for "
                          "backup %s :") % id
            raise exception.BackupUpdateError(str(ex))


def persisted_models():
    return {'backups': DBBackup}


class DBBackup(DatabaseModelBase):
    """A table for Backup records"""
    _data_fields = ['id', 'name', 'description', 'location', 'backup_type',
                    'size', 'tenant_id', 'state', 'instance_id',
                    'backup_timestamp', 'deleted', 'created',
                    'updated', 'deleted_at']
