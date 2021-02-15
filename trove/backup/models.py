# Copyright [2013] Hewlett-Packard Development Company, L.P.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Model classes that form the core of snapshots functionality."""

from oslo_log import log as logging
from requests.exceptions import ConnectionError
from sqlalchemy import desc
from swiftclient.client import ClientException

from trove.backup.state import BackupState
from trove.common import cfg
from trove.common import clients
from trove.common import constants
from trove.common import exception
from trove.common import swift
from trove.common import utils
from trove.common.i18n import _
from trove.datastore import models as datastore_models
from trove.db.models import DatabaseModelBase
from trove.quota.quota import run_with_quotas
from trove.taskmanager import api

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Backup(object):

    @classmethod
    def validate_can_perform_action(cls, instance, operation):
        """
        Raises exception if backup strategy is not supported
        """
        datastore_cfg = CONF.get(instance.datastore_version.manager)
        if not datastore_cfg or not (
                datastore_cfg.get('backup_strategy', None)):
            raise exception.DatastoreOperationNotSupported(
                operation=operation, datastore=instance.datastore.name)

    @classmethod
    def create(cls, context, instance, name, description=None,
               parent_id=None, incremental=False, swift_container=None,
               restore_from=None):
        """
        create db record for Backup
        :param cls:
        :param context: tenant_id included
        :param instance:
        :param name:
        :param description:
        :param parent_id:
        :param incremental: flag to indicate incremental backup
                            based on previous backup
        :param swift_container: Swift container name.
        :param restore_from: A dict that contains backup information of another
                             region.
        :return:
        """
        backup_state = BackupState.NEW
        checksum = None
        instance_id = None
        parent = None
        last_backup_id = None
        location = None
        backup_type = constants.BACKUP_TYPE_FULL
        size = None

        if restore_from:
            # Check location and datastore version.
            LOG.info(f"Restoring backup, restore_from: {restore_from}")
            backup_state = BackupState.RESTORED

            ds_version_id = restore_from.get('local_datastore_version_id')
            ds_version = datastore_models.DatastoreVersion.load_by_uuid(
                ds_version_id)

            location = restore_from.get('remote_location')
            swift_client = clients.create_swift_client(context)
            try:
                obj_meta = swift.get_metadata(swift_client, location,
                                              extra_attrs=['etag'])
            except Exception:
                msg = f'Failed to restore backup from {location}'
                LOG.exception(msg)
                raise exception.BackupCreationError(msg)

            checksum = obj_meta['etag']
            if 'parent_location' in obj_meta:
                backup_type = constants.BACKUP_TYPE_INC

            size = restore_from['size']
        else:
            instance_id = utils.get_id_from_href(instance)
            # Import here to avoid circular imports.
            from trove.instance import models as inst_model
            instance_model = inst_model.Instance.load(context, instance_id)
            instance_model.validate_can_perform_action()
            if instance_model.cluster_id is not None:
                raise exception.ClusterInstanceOperationNotSupported()

            cls.validate_can_perform_action(instance_model, 'backup_create')

            cls.verify_swift_auth_token(context)

            ds = instance_model.datastore
            ds_version = instance_model.datastore_version

            if parent_id:
                # Look up the parent info or fail early if not found or if
                # the user does not have access to the parent.
                _parent = cls.get_by_id(context, parent_id)
                parent = {
                    'location': _parent.location,
                    'checksum': _parent.checksum,
                }
            elif incremental:
                _parent = Backup.get_last_completed(context, instance_id)
                if _parent:
                    parent = {
                        'location': _parent.location,
                        'checksum': _parent.checksum
                    }
                    last_backup_id = _parent.id

            if parent:
                backup_type = constants.BACKUP_TYPE_INC

        def _create_resources():
            try:
                db_info = DBBackup.create(
                    name=name,
                    description=description,
                    tenant_id=context.project_id,
                    state=backup_state,
                    instance_id=instance_id,
                    parent_id=parent_id or last_backup_id,
                    datastore_version_id=ds_version.id,
                    deleted=False,
                    location=location,
                    checksum=checksum,
                    backup_type=backup_type,
                    size=size
                )
            except exception.InvalidModelError as ex:
                LOG.exception("Unable to create backup record for "
                              "instance: %s", instance_id)
                raise exception.BackupCreationError(str(ex))

            if not restore_from:
                backup_info = {
                    'id': db_info.id,
                    'name': name,
                    'description': description,
                    'instance_id': instance_id,
                    'backup_type': db_info.backup_type,
                    'checksum': db_info.checksum,
                    'parent': parent,
                    'datastore': ds.name,
                    'datastore_version': ds_version.name,
                    'swift_container': swift_container
                }
                api.API(context).create_backup(backup_info, instance_id)
            else:
                context.notification.payload.update(
                    {'backup_id': db_info.id}
                )

            return db_info

        return run_with_quotas(context.project_id, {'backups': 1},
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
    def list(cls, context, datastore=None, instance_id=None, project_id=None,
             all_projects=False):
        query = DBBackup.query()
        filters = [DBBackup.deleted == 0]

        if project_id:
            filters.append(DBBackup.tenant_id == project_id)
        elif not all_projects:
            filters.append(DBBackup.tenant_id == context.project_id)

        if instance_id:
            filters.append(DBBackup.instance_id == instance_id)

        if datastore:
            ds = datastore_models.Datastore.load(datastore)
            filters.append(datastore_models.DBDatastoreVersion.
                           datastore_id == ds.id)
            query = query.join(datastore_models.DBDatastoreVersion)

        query = query.filter(*filters)
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
        if context.is_admin:
            query = query.filter_by(instance_id=instance_id,
                                    deleted=False)
        else:
            query = query.filter_by(instance_id=instance_id,
                                    tenant_id=context.project_id,
                                    deleted=False)
        return cls._paginate(context, query)

    @classmethod
    def get_last_completed(cls, context, instance_id,
                           include_incremental=True):
        """
        returns last completed backup
        :param cls:
        :param instance_id:
        :param include_incremental:
        :return:
        """
        last_backup = None
        backups, marker = cls.list_for_instance(context, instance_id)
        # we don't care about the marker since we only want the first backup
        # and they are ordered descending based on date (what we want)
        for backup in backups:
            if backup.state == BackupState.COMPLETED and (
                    include_incremental or not backup.parent_id):
                if not last_backup or backup.updated > last_backup.updated:
                    last_backup = backup

        return last_backup

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

        # Recursively delete all children and grandchildren of this backup.
        query = DBBackup.query()
        query = query.filter_by(parent_id=backup_id, deleted=False)
        for child in query.all():
            try:
                cls.delete(context, child.id)
            except exception.NotFound:
                LOG.warning("Backup %s cannot be found.", backup_id)

        def _delete_resources():
            backup = cls.get_by_id(context, backup_id)
            if backup.is_running:
                msg = _("Backup %s cannot be deleted because it is running.")
                raise exception.UnprocessableEntity(msg % backup_id)
            cls.verify_swift_auth_token(context)
            api.API(context).delete_backup(backup_id)

        return run_with_quotas(context.project_id,
                               {'backups': -1},
                               _delete_resources)

    @classmethod
    def verify_swift_auth_token(cls, context):
        try:
            client = clients.create_swift_client(context)
            client.get_account()
        except ClientException:
            raise exception.SwiftAuthError(tenant_id=context.project_id)
        except exception.NoServiceEndpoint:
            raise exception.SwiftNotFound(tenant_id=context.project_id)
        except ConnectionError:
            raise exception.SwiftConnectionError()


class BackupStrategy(object):
    @classmethod
    def create(cls, context, instance_id, swift_container):
        try:
            existing = DBBackupStrategy.find_by(tenant_id=context.project_id,
                                                instance_id=instance_id)
            existing.swift_container = swift_container
            existing.save()
            return existing
        except exception.NotFound:
            return DBBackupStrategy.create(
                tenant_id=context.project_id,
                instance_id=instance_id,
                backend='swift',
                swift_container=swift_container,
            )

    @classmethod
    def list(cls, context, tenant_id, instance_id=None):
        kwargs = {'tenant_id': tenant_id}
        if instance_id:
            kwargs['instance_id'] = instance_id
        result = DBBackupStrategy.find_by_filter(**kwargs)
        return result

    @classmethod
    def get(cls, context, instance_id):
        try:
            return DBBackupStrategy.find_by(tenant_id=context.project_id,
                                            instance_id=instance_id)
        except exception.NotFound:
            try:
                return DBBackupStrategy.find_by(tenant_id=context.project_id,
                                                instance_id='')
            except exception.NotFound:
                return None

    @classmethod
    def delete(cls, context, tenant_id, instance_id):
        try:
            existing = DBBackupStrategy.find_by(tenant_id=tenant_id,
                                                instance_id=instance_id)
            existing.delete()
        except exception.NotFound:
            pass


def persisted_models():
    return {'backups': DBBackup, 'backup_strategy': DBBackupStrategy}


class DBBackup(DatabaseModelBase):
    """A table for Backup records."""
    _data_fields = ['name', 'description', 'location', 'backup_type',
                    'size', 'tenant_id', 'state', 'instance_id',
                    'checksum', 'backup_timestamp', 'deleted', 'created',
                    'updated', 'deleted_at', 'parent_id',
                    'datastore_version_id']
    _table_name = 'backups'

    @property
    def is_running(self):
        return self.state in BackupState.RUNNING_STATES

    @property
    def is_done(self):
        return self.state in BackupState.END_STATES

    @property
    def is_done_successfuly(self):
        return self.state in [BackupState.COMPLETED, BackupState.RESTORED]

    @property
    def filename(self):
        if self.location:
            last_slash = self.location.rfind("/")
            if last_slash < 0:
                raise ValueError(_("Bad location for backup object: %s")
                                 % self.location)
            return self.location[last_slash + 1:]
        else:
            return None

    @property
    def container_name(self):
        if self.location:
            return self.location.split('/')[-2]
        else:
            return None

    @property
    def datastore(self):
        if self.datastore_version_id:
            return datastore_models.Datastore.load(
                self.datastore_version.datastore_id)

    @property
    def datastore_version(self):
        if self.datastore_version_id:
            return datastore_models.DatastoreVersion.load_by_uuid(
                self.datastore_version_id)

    def check_swift_object_exist(self, context, verify_checksum=False):
        try:
            parts = self.location.split('/')
            obj = parts[-1]
            container = parts[-2]
            client = clients.create_swift_client(context)
            LOG.debug("Checking if backup exists in %s", self.location)
            resp = client.head_object(container, obj)
            if verify_checksum:
                LOG.debug("Checking if backup checksum matches swift "
                          "for backup %s", self.id)
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
                raise exception.SwiftAuthError(tenant_id=context.project_id)


class DBBackupStrategy(DatabaseModelBase):
    """A table for backup strategy records."""
    _data_fields = ['tenant_id', 'instance_id', 'backend', 'swift_container']
    _table_name = 'backup_strategy'
