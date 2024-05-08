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

"""init trove db

Revision ID: 906cffda7b29
Revises:
Create Date: 2024-04-30 13:58:12.700444
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, \
    String, Text, UniqueConstraint
from sqlalchemy.sql import table, column
from trove.common import cfg

CONF = cfg.CONF


# revision identifiers, used by Alembic.
revision: str = '906cffda7b29'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    bind = op.get_bind()

    """ merges the schmas up to 048 are treated asis.
    049 is saved as another revision
    """

    """001_base_schema.py
    """
    # NOTE(hiwkby)
    # move the 001_base_schema.py to 032_clusters.py because
    # instances references foreign keys in clusters and other tables
    # that are created at 032_clusters.py.

    """002_service_images.py
    """
    op.create_table(
        'service_images',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('service_name', String(255)),
        Column('image_id', String(255))
    )

    """003_service_statuses.py
    """
    op.create_table(
        'service_statuses',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('instance_id', String(36), nullable=False),
        Column('status_id', Integer(), nullable=False),
        Column('status_description', String(64), nullable=False),
        Column('updated_at', DateTime()),
    )
    op.create_index('service_statuses_instance_id', 'service_statuses',
                    ['instance_id'])

    """004_root_enabled.py
    """
    op.create_table(
        'root_enabled_history',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user', String(length=255)),
        Column('created', DateTime()),
    )

    """005_heartbeat.py
    """
    op.create_table(
        'agent_heartbeats',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('instance_id', String(36), nullable=False, index=True,
               unique=True),
        Column('guest_agent_version', String(255), index=True),
        Column('deleted', Boolean(), index=True),
        Column('deleted_at', DateTime()),
        Column('updated_at', DateTime(), nullable=False)
    )

    """006_dns_records.py
    """
    op.create_table(
        'dns_records',
        Column('name', String(length=255), primary_key=True),
        Column('record_id', String(length=64))
    )

    """007_add_volume_flavor.py
    """
    # added the columns to instances table

    """008_add_instance_fields.py
    """
    # added the columns to instances table

    """009_add_deleted_flag_to_instances.py
    """
    # added the columns to instances table

    """010_add_usage.py
    """
    op.create_table(
        'usage_events',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('instance_name', String(36)),
        Column('tenant_id', String(36)),
        Column('nova_instance_id', String(36)),
        Column('instance_size', Integer()),
        Column('nova_volume_id', String(36)),
        Column('volume_size', Integer()),
        Column('end_time', DateTime()),
        Column('updated', DateTime()),
    )

    """011_quota.py
    """
    op.create_table(
        'quotas',
        Column('id', String(36),
               primary_key=True, nullable=False),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('tenant_id', String(36)),
        Column('resource', String(length=255), nullable=False),
        Column('hard_limit', Integer()),
        UniqueConstraint('tenant_id', 'resource')
    )

    op.create_table(
        'quota_usages',
        Column('id', String(36),
               primary_key=True, nullable=False),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('tenant_id', String(36)),
        Column('in_use', Integer(), default=0),
        Column('reserved', Integer(), default=0),
        Column('resource', String(length=255), nullable=False),
        UniqueConstraint('tenant_id', 'resource')
    )

    op.create_table(
        'reservations',
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('id', String(36),
               primary_key=True, nullable=False),
        Column('usage_id', String(36)),
        Column('delta', Integer(), nullable=False),
        Column('status', String(length=36))
    )

    """012_backup.py
    """
    # NOTE(hiwkby)
    # move the 012_backup.py to 029_add_backup_datastore.py because
    # backups references a datastore_versions.id as a foreign key
    # that are created at 012_backup.py.

    """013_add_security_group_artifacts.py
    """
    op.create_table(
        'security_groups',
        Column('id', String(length=36), primary_key=True, nullable=False),
        Column('name', String(length=255)),
        Column('description', String(length=255)),
        Column('user', String(length=255)),
        Column('tenant_id', String(length=255)),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('deleted', Boolean(), default=0),
        Column('deleted_at', DateTime()),
    )

    # NOTE(hiwkby)
    # move the security_group_instance_associations schema
    # to 032_clusters.py where instances table is created.

    op.create_table(
        'security_group_rules',
        Column('id', String(length=36), primary_key=True, nullable=False),
        Column('group_id', String(length=36),
               ForeignKey('security_groups.id', ondelete='CASCADE',
                          onupdate='CASCADE')),
        Column('parent_group_id', String(length=36),
               ForeignKey('security_groups.id', ondelete='CASCADE',
                          onupdate='CASCADE')),
        Column('protocol', String(length=255)),
        Column('from_port', Integer()),
        Column('to_port', Integer()),
        Column('cidr', String(length=255)),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('deleted', Boolean(), default=0),
        Column('deleted_at', DateTime()),
    )

    """014_update_instance_flavor_id.py
    """
    # updated the instances table schema

    """015_add_service_type.py
    """
    # updated the instances table schema
    # NOTE(hiwkby)
    # service_type was deleted in 016_add_datastore_type.py

    """016_add_datastore_type.py
    """
    op.create_table(
        'datastores',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('name', String(255), unique=True),
        # NOTE(hiwkby) manager was dropped in 017_update_datastores.py
        # Column('manager', String(255), nullable=False),
        Column('default_version_id', String(36)),
    )
    op.create_table(
        'datastore_versions',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('datastore_id', String(36), ForeignKey('datastores.id')),
        # NOTE(hiwkby)
        # unique=false in 018_datastore_versions_fix.py
        Column('name', String(255), unique=False),
        Column('image_id', String(36), nullable=True),
        Column('packages', String(511)),
        Column('active', Boolean(), nullable=False),
        # manager added in 017_update_datastores.py
        Column('manager', String(255)),
        # image_tags added in 047_image_tag_in_datastore_version.py
        Column('image_tags', String(255), nullable=True),
        # version added in 048_add_version_to_datastore_version.py
        Column('version', String(255), nullable=True),
        UniqueConstraint('datastore_id', 'name', 'version',
                         name='ds_versions')
    )

    """017_update_datastores.py
    """
    # updated the datastores and datastore_versions table schema.

    """018_datastore_versions_fix.py
    """
    # updated the datastore_versions table schema

    """019_datastore_fix.py
    """
    # updated the datastore_versions table schema

    """020_configurations.py
    """
    op.create_table(
        'configurations',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('name', String(64), nullable=False),
        Column('description', String(256)),
        Column('tenant_id', String(36), nullable=False),
        Column('datastore_version_id', String(36), nullable=False),
        Column('deleted', Boolean(), nullable=False, default=False),
        Column('deleted_at', DateTime()),
        # NOTE(hiwkby)
        # created added in 031_add_timestamps_to_configurations.py
        Column('created', DateTime()),
        Column('updated', DateTime()),
    )

    op.create_table(
        'configuration_parameters',
        Column('configuration_id', String(36), ForeignKey('configurations.id'),
               nullable=False, primary_key=True),
        Column('configuration_key', String(128),
               nullable=False, primary_key=True),
        Column('configuration_value', String(128)),
        Column('deleted', Boolean(), nullable=False, default=False),
        Column('deleted_at', DateTime()),
    )

    """021_conductor_last_seen.py
    """
    op.create_table(
        'conductor_lastseen',
        Column('instance_id', String(36), primary_key=True, nullable=False),
        Column('method_name', String(36), primary_key=True, nullable=False),
        Column('sent', Float(precision=32))
    )

    """022_add_backup_parent_id.py
    """
    # updated the backups table schema

    """023_add_instance_indexes.py
    """
    # updated the instances table schema

    """024_add_backup_indexes.py
    """
    # updated the backups table schema

    """025_add_service_statuses_indexes.py
    """
    # updated the service_statuses table schema

    """026_datastore_versions_unique_fix.py
    """
    # updated the datastore_versions table schema

    """027_add_datastore_capabilities.py
    """
    op.create_table(
        'capabilities',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('name', String(255), unique=True),
        Column('description', String(255), nullable=False),
        Column('enabled', Boolean()),
    )

    op.create_table(
        'capability_overrides',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('datastore_version_id', String(36),
               ForeignKey('datastore_versions.id')),
        Column('capability_id', String(36), ForeignKey('capabilities.id')),
        Column('enabled', Boolean()),
        UniqueConstraint('datastore_version_id', 'capability_id',
                         name='idx_datastore_capabilities_enabled')
    )

    """028_recreate_agent_heartbeat.py
    """
    # updated the datastore_versions table schema

    """029_add_backup_datastore.py
    """
    # NOTE(hiwkby)
    # moves here from 012_backup.py because
    # backups references datastore_versions.id as a foreign key
    op.create_table(
        'backups',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('name', String(255), nullable=False),
        Column('description', String(512)),
        Column('location', String(1024)),
        Column('backup_type', String(32)),
        Column('size', Float()),
        Column('tenant_id', String(36)),
        Column('state', String(32), nullable=False),
        Column('instance_id', String(36)),
        Column('checksum', String(32)),
        Column('backup_timestamp', DateTime()),
        Column('deleted', Boolean(), default=0),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('deleted_at', DateTime()),
        # 022_add_backup_parent_id.py
        Column('parent_id', String(36), nullable=True),
        # 029_add_backup_datastore.py
        Column('datastore_version_id', String(36),
               ForeignKey(
                   "datastore_versions.id",
                   name="backups_ibfk_1")),
    )
    op.create_index('backups_instance_id', 'backups', ['instance_id'])
    op.create_index('backups_deleted', 'backups', ['deleted'])

    """030_add_master_slave.py
    """
    # updated the instances table schema

    """031_add_timestamps_to_configurations.py
    """
    # updated the configurations table schema

    """032_clusters.py
    """
    op.create_table(
        'clusters',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('created', DateTime(), nullable=False),
        Column('updated', DateTime(), nullable=False),
        Column('name', String(255), nullable=False),
        Column('task_id', Integer(), nullable=False),
        Column('tenant_id', String(36), nullable=False),
        Column('datastore_version_id', String(36),
               ForeignKey(
                   "datastore_versions.id",
                   name="clusters_ibfk_1"),
               nullable=False),
        Column('deleted', Boolean()),
        Column('deleted_at', DateTime()),
        Column('configuration_id', String(36),
               ForeignKey(
                   "configurations.id",
                   name="clusters_ibfk_2")),
    )

    op.create_index('clusters_tenant_id', 'clusters', ['tenant_id'])
    op.create_index('clusters_deleted', 'clusters', ['deleted'])

    # NOTE(hiwkby)
    # move here from the 001_base_schema.py because
    # instances references cluster and other tables as foreign keys
    op.create_table(
        'instances',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('name', String(255)),
        Column('hostname', String(255)),
        Column('compute_instance_id', String(36)),
        Column('task_id', Integer()),
        Column('task_description', String(255)),
        Column('task_start_time', DateTime()),
        Column('volume_id', String(36)),
        Column('flavor_id', String(255)),
        Column('volume_size', Integer()),
        Column('tenant_id', String(36), nullable=True),
        Column('server_status', String(64)),
        Column('deleted', Boolean()),
        Column('deleted_at', DateTime()),
        Column('datastore_version_id', String(36),
               ForeignKey(
                   "datastore_versions.id",
                   name="instances_ibfk_1"), nullable=True),
        Column('configuration_id', String(36),
               ForeignKey(
                   "configurations.id",
                   name="instances_ibfk_2")),
        Column('slave_of_id', String(36),
               ForeignKey(
                   "instances.id",
                   name="instances_ibfk_3"), nullable=True),
        Column('cluster_id', String(36),
               ForeignKey(
                   "clusters.id",
                   name="instances_ibfk_4")),
        Column('shard_id', String(36)),
        Column('type', String(64)),
        Column('region_id', String(255)),
        Column('encrypted_key', String(255)),
        Column('access', Text(), nullable=True),
    )
    op.create_index('instances_tenant_id', 'instances', ['tenant_id'])
    op.create_index('instances_deleted', 'instances', ['deleted'])
    op.create_index('instances_cluster_id', 'instances', ['cluster_id'])

    # NOTE(hiwkby)
    # move here from the security_group_instance_associations schema
    # because it references instances.id as a foreign key
    op.create_table(
        'security_group_instance_associations',
        Column('id', String(length=36), primary_key=True, nullable=False),
        Column('security_group_id', String(length=36),
               ForeignKey('security_groups.id', ondelete='CASCADE',
                          onupdate='CASCADE')),
        Column('instance_id', String(length=36),
               ForeignKey('instances.id', ondelete='CASCADE',
                          onupdate='CASCADE')),
        Column('created', DateTime()),
        Column('updated', DateTime()),
        Column('deleted', Boolean(), default=0),
        Column('deleted_at', DateTime())
    )

    """033_datastore_parameters.py
    """
    op.create_table(
        'datastore_configuration_parameters',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('name', String(128), primary_key=True, nullable=False),
        Column('datastore_version_id', String(36),
               ForeignKey("datastore_versions.id"),
               primary_key=True, nullable=False),
        Column('restart_required', Boolean(), nullable=False, default=False),
        Column('max_size', String(40)),
        Column('min_size', String(40)),
        Column('data_type', String(128), nullable=False),
        UniqueConstraint(
            'datastore_version_id', 'name',
            name='UQ_datastore_configuration_parameters_datastore_version_id_name')  # noqa
    )

    """034_change_task_description.py
    """
    # updated the configurations table schema

    """035_flavor_id_int_to_string.py
    """
    # updated the configurations table schema

    """036_add_datastore_version_metadata.py
    """
    op.create_table(
        'datastore_version_metadata',
        Column('id', String(36), primary_key=True, nullable=False),
        Column(
            'datastore_version_id',
            String(36),
            ForeignKey('datastore_versions.id', ondelete='CASCADE'),
        ),
        Column('key', String(128), nullable=False),
        Column('value', String(128)),
        Column('created', DateTime(), nullable=False),
        Column('deleted', Boolean(), nullable=False, default=False),
        Column('deleted_at', DateTime()),
        Column('updated_at', DateTime()),
        UniqueConstraint(
            'datastore_version_id', 'key', 'value',
            name='UQ_datastore_version_metadata_datastore_version_id_key_value') # noqa
    )

    """037_modules.py
    """
    is_nullable = True if bind.engine.name == "sqlite" else False
    op.create_table(
        'modules',
        Column('id', String(length=64), primary_key=True, nullable=False),
        Column('name', String(length=255), nullable=False),
        Column('type', String(length=255), nullable=False),
        # contents was updated in 40_module_priority.py
        Column('contents', Text(length=4294967295), nullable=False),
        Column('description', String(length=255)),
        Column('tenant_id', String(length=64), nullable=True),
        Column('datastore_id', String(length=64), nullable=True),
        Column('datastore_version_id', String(length=64), nullable=True),
        Column('auto_apply', Boolean(), default=0, nullable=False),
        Column('visible', Boolean(), default=1, nullable=False),
        Column('live_update', Boolean(), default=0, nullable=False),
        Column('md5', String(length=32), nullable=False),
        Column('created', DateTime(), nullable=False),
        Column('updated', DateTime(), nullable=False),
        Column('deleted', Boolean(), default=0, nullable=False),
        Column('deleted_at', DateTime()),
        UniqueConstraint(
            'type', 'tenant_id', 'datastore_id', 'datastore_version_id',
            'name', 'deleted_at',
            name='UQ_type_tenant_datastore_datastore_version_name'),
        # NOTE(hiwkby)
        # the following columns added in 040_module_priority.py
        Column('priority_apply', Boolean(), nullable=is_nullable, default=0),
        Column('apply_order', Integer(), nullable=is_nullable, default=5),
        Column('is_admin', Boolean(), nullable=is_nullable, default=0),
    )

    op.create_table(
        'instance_modules',
        Column('id', String(length=64), primary_key=True, nullable=False),
        Column('instance_id', String(length=64),
               ForeignKey('instances.id', ondelete="CASCADE",
                          onupdate="CASCADE"), nullable=False),
        Column('module_id', String(length=64),
               ForeignKey('modules.id', ondelete="CASCADE",
                          onupdate="CASCADE"), nullable=False),
        Column('md5', String(length=32), nullable=False),
        Column('created', DateTime(), nullable=False),
        Column('updated', DateTime(), nullable=False),
        Column('deleted', Boolean(), default=0, nullable=False),
        Column('deleted_at', DateTime()),
    )

    """038_instance_faults.py
    """
    op.create_table(
        'instance_faults',
        Column('id', String(length=64), primary_key=True, nullable=False),
        Column('instance_id', String(length=64),
               ForeignKey('instances.id', ondelete="CASCADE",
                          onupdate="CASCADE"), nullable=False),
        Column('message', String(length=255), nullable=False),
        Column('details', Text(length=65535), nullable=False),
        Column('created', DateTime(), nullable=False),
        Column('updated', DateTime(), nullable=False),
        Column('deleted', Boolean(), default=0, nullable=False),
        Column('deleted_at', DateTime()),
    )

    """039_region.py
    """
    instances = table("instances", column("region_id", String))
    op.execute(
        instances.update()
        .values({"region_id": CONF.service_credentials.region_name})
    )

    """040_module_priority.py
    """
    # updated the modules table schema

    """041_instance_keys.py
    """
    # updated the instances table schema

    """042_add_cluster_configuration_id.py
    """
    # updated the clusters table schema

    """043_instance_ds_version_nullable.py
    """
    # updated the instances table schema

    """044_remove_datastore_configuration_parameters_deleted.py
    """
    # updated the datastore_configuration_parameters table schema

    """045_add_backup_strategy.py
    """
    op.create_table(
        'backup_strategy',
        Column('id', String(36), primary_key=True, nullable=False),
        Column('tenant_id', String(36), nullable=False),
        Column('instance_id', String(36), nullable=False, default=''),
        Column('backend', String(255), nullable=False),
        Column('swift_container', String(255), nullable=True),
        Column('created', DateTime()),
        UniqueConstraint(
            'tenant_id', 'instance_id',
            name='UQ_backup_strategy_tenant_id_instance_id'),
    )
    op.create_index('backup_strategy_tenant_id_instance_id',
                    'backup_strategy', ['tenant_id', 'instance_id'])

    """046_add_access_to_instance.py
    """
    # updated the instances table schema

    """047_image_tag_in_datastore_version.py
    """
    # updated the datastore_versions table schema

    """048_add_version_to_datastore_version.py
    """
    # updated the datastore_versions table schema

    """049_add_registry_ext_to_datastore_version.py
    """


def downgrade() -> None:
    pass
