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

from sqlalchemy import desc
from swiftclient.client import ClientException

from trove.common import cfg
from trove.common import exception
from trove.db.models import DatabaseModelBase
from trove.openstack.common import log as logging
from trove.taskmanager import api
from trove.common.remote import create_swift_client
from trove.common import utils
from trove.quota.quota import run_with_quotas

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
SWIFT_CONTAINER = CONF.backup_swift_container


class BackupState(object):
    NEW = "NEW"
    BUILDING = "BUILDING"
    SAVING = "SAVING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DELETE_FAILED = "DELETE_FAILED"
    RUNNING_STATES = [NEW, BUILDING, SAVING]
    END_STATES = [COMPLETED, FAILED, DELETE_FAILED]


class Backup(object):

    @classmethod
    def create(cls, context, instance, name, description=None):
        """
        create db record for Backup
        :param cls:
        :param context: tenant_id included
        :param instance:
        :param name:
        :param description:
        :return:
        """

        def _create_resources():
            # parse the ID from the Ref
            instance_id = utils.get_id_from_href(instance)

            # verify that the instance exists and can perform actions
            from trove.instance.models import Instance
            instance_model = Instance.load(context, instance_id)
            instance_model.validate_can_perform_action()

            cls.verify_swift_auth_token(context)

            try:
                db_info = DBBackup.create(name=name,
                                          description=description,
                                          tenant_id=context.tenant,
                                          state=BackupState.NEW,
                                          instance_id=instance_id,
                                          deleted=False)
            except exception.InvalidModelError as ex:
                LOG.exception("Unable to create Backup record:")
                raise exception.BackupCreationError(str(ex))

            backup_info = {'id': db_info.id,
                           'name': name,
                           'description': description,
                           'instance_id': instance_id,
                           'backup_type': db_info.backup_type,
                           'checksum': db_info.checksum,
                           }
            api.API(context).create_backup(backup_info, instance_id)
            return db_info

        return run_with_quotas(context.tenant,
                               {'backups': 1},
                               _create_resources)

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
    def get_by_id(cls, context, backup_id, deleted=False):
        """
        get the backup for that id
        :param cls:
        :param backup_id: Id of the backup to return
        :param deleted: Return deleted backups
        :return:
        """
        try:
            db_info = DBBackup.find_by(context=context,
                                       id=backup_id,
                                       deleted=deleted)
            return db_info
        except exception.NotFound:
            raise exception.NotFound(uuid=backup_id)

    @classmethod
    def _paginate(cls, context, query):
        """Paginate the results of the base query.
        We use limit/offset as the results need to be ordered by date
        and not the primary key.
        """
        marker = int(context.marker or 0)
        limit = int(context.limit or CONF.backups_page_size)
        # order by 'updated DESC' to show the most recent backups first
        query = query.order_by(desc(DBBackup.updated))
        # Apply limit/offset
        query = query.limit(limit)
        query = query.offset(marker)
        # check if we need to send a marker for the next page
        if query.count() < limit:
            marker = None
        else:
            marker += limit
        return query.all(), marker

    @classmethod
    def list(cls, context):
        """
        list all live Backups belong to given tenant
        :param cls:
        :param context: tenant_id included
        :return:
        """
        query = DBBackup.query()
        query = query.filter_by(tenant_id=context.tenant,
                                deleted=False)
        return cls._paginate(context, query)

    @classmethod
    def list_for_instance(cls, context, instance_id):
        """
        list all live Backups associated with given instance
        :param cls:
        :param instance_id:
        :return:
        """
        query = DBBackup.query()
        query = query.filter_by(instance_id=instance_id,
                                deleted=False)
        return cls._paginate(context, query)

    @classmethod
    def fail_for_instance(cls, instance_id):
        query = DBBackup.query()
        query = query.filter(DBBackup.instance_id == instance_id,
                             DBBackup.state.in_(BackupState.RUNNING_STATES))
        query = query.filter_by(deleted=False)
        for backup in query.all():
            backup.state = BackupState.FAILED
            backup.save()

    @classmethod
    def delete(cls, context, backup_id):
        """
        update Backup table on deleted flag for given Backup
        :param cls:
        :param context: context containing the tenant id and token
        :param backup_id: Backup uuid
        :return:
        """

        def _delete_resources():
            backup = cls.get_by_id(context, backup_id)
            if backup.is_running:
                msg = ("Backup %s cannot be delete because it is running." %
                       backup_id)
                raise exception.UnprocessableEntity(msg)
            cls.verify_swift_auth_token(context)
            api.API(context).delete_backup(backup_id)

        return run_with_quotas(context.tenant,
                               {'backups': -1},
                               _delete_resources)

    @classmethod
    def verify_swift_auth_token(cls, context):
        try:
            client = create_swift_client(context)
            client.get_account()
        except ClientException:
            raise exception.SwiftAuthError(tenant_id=context.tenant)


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

    @property
    def filename(self):
        if self.location:
            last_slash = self.location.rfind("/")
            if last_slash < 0:
                raise ValueError("Bad location for backup object.")
            return self.location[last_slash + 1:]
        else:
            return None

    def check_swift_object_exist(self, context, verify_checksum=False):
        try:
            parts = self.location.split('/')
            obj = parts[-1]
            container = parts[-2]
            client = create_swift_client(context)
            LOG.info(_("Checking if backup exist in '%s'") % self.location)
            resp = client.head_object(container, obj)
            if verify_checksum:
                LOG.info(_("Checking if backup checksum matches swift."))
                # swift returns etag in double quotes
                # e.g. '"dc3b0827f276d8d78312992cc60c2c3f"'
                swift_checksum = resp['etag'].strip('"')
                if self.checksum != swift_checksum:
                    raise exception.RestoreBackupIntegrityError(
                        backup_id=self.id)
            return True
        except ClientException as e:
            if e.http_status == 404:
                return False
            else:
                raise exception.SwiftAuthError(tenant_id=context.tenant)
