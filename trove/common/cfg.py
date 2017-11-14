# copyright 2011 OpenStack Foundation
# Copyright 2014 Rackspace Hosting
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
"""Routines for configuring Trove."""

import os.path

from oslo_config import cfg
from oslo_config.cfg import NoSuchOptError
from oslo_config import types
from oslo_log import log as logging
from oslo_middleware import cors
from osprofiler import opts as profiler

from trove.common.i18n import _
from trove.version import version_info as version

ListOfPortsType = types.Range(1, 65535)

LOG = logging.getLogger(__name__)
UNKNOWN_SERVICE_ID = 'unknown-service-id-error'
HEAT_REMOVAL_DEPRECATION_WARNING = _('Support for heat templates in Trove is '
                                     'scheduled for removal. You will no '
                                     'longer be able to provide a heat '
                                     'template to Trove for the provisioning '
                                     'of resources.')

path_opts = [
    cfg.StrOpt('pybasedir',
               default=os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    '../')),
               help='Directory where the Trove python module is installed.'),
]

common_opts = [
    cfg.IPOpt('bind_host', default='0.0.0.0',
              help='IP address the API server will listen on.'),
    cfg.PortOpt('bind_port', default=8779,
                help='Port the API server will listen on.'),
    cfg.StrOpt('api_paste_config', default="api-paste.ini",
               help='File name for the paste.deploy config for trove-api.'),
    cfg.BoolOpt('trove_volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.ListOpt('admin_roles', default=['admin'],
                help='Roles to add to an admin user.'),
    cfg.BoolOpt('update_status_on_fail', default=True,
                help='Set the service and instance task statuses to ERROR '
                     'when an instance fails to become active within the '
                     'configured usage_timeout.'),
    cfg.StrOpt('os_region_name', default='RegionOne',
               help='Region name of this node. Used when searching catalog.'),
    cfg.URIOpt('nova_compute_url', help='URL without the tenant segment.'),
    cfg.StrOpt('nova_compute_service_type', default='compute',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('nova_compute_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.StrOpt('nova_client_version', default='2.12',
               help="The version of the compute service client."),
    cfg.StrOpt('glance_client_version', default='2',
               help="The version of the image service client."),
    cfg.BoolOpt('nova_api_insecure', default=False,
                help="Allow to perform insecure SSL requests to nova."),
    cfg.URIOpt('neutron_url', help='URL without the tenant segment.'),
    cfg.StrOpt('neutron_service_type', default='network',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('neutron_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.BoolOpt('neutron_api_insecure', default=False,
                help="Allow to perform insecure SSL requests to neutron."),
    cfg.URIOpt('cinder_url', help='URL without the tenant segment.'),
    cfg.StrOpt('cinder_service_type', default='volumev2',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('cinder_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.BoolOpt('cinder_api_insecure', default=False,
                help="Allow to perform insecure SSL requests to cinder."),
    cfg.URIOpt('swift_url', help='URL ending in ``AUTH_``.'),
    cfg.StrOpt('swift_service_type', default='object-store',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('swift_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.BoolOpt('swift_api_insecure', default=False,
                help="Allow to perform insecure SSL requests to swift."),
    cfg.URIOpt('glance_url', help='URL ending in ``AUTH_``.'),
    cfg.StrOpt('glance_service_type', default='image',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('glance_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.URIOpt('trove_auth_url', default='http://0.0.0.0/identity/v2.0',
               help='Trove authentication URL.'),
    cfg.StrOpt('trove_url', help='URL without the tenant segment.'),
    cfg.StrOpt('trove_service_type', default='database',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('trove_endpoint_type', default='publicURL',
               help='Service endpoint type to use when searching catalog.'),
    cfg.IPOpt('host', default='0.0.0.0',
              help='Host to listen for RPC messages.'),
    cfg.IntOpt('report_interval', default=30,
               help='The interval (in seconds) which periodic tasks are run.'),
    cfg.BoolOpt('trove_dns_support', default=False,
                help='Whether Trove should add DNS entries on create '
                     '(using Designate DNSaaS).'),
    cfg.StrOpt('db_api_implementation', default='trove.db.sqlalchemy.api',
               help='API Implementation for Trove database access.'),
    cfg.StrOpt('dns_driver', default='trove.dns.driver.DnsDriver',
               help='Driver for DNSaaS.'),
    cfg.StrOpt('dns_instance_entry_factory',
               default='trove.dns.driver.DnsInstanceEntryFactory',
               help='Factory for adding DNS entries.'),
    cfg.HostnameOpt('dns_hostname', default="localhost",
                    help='Hostname used for adding DNS entries.'),
    cfg.StrOpt('dns_account_id', default="",
               help='Tenant ID for DNSaaS.'),
    cfg.URIOpt('dns_endpoint_url', default="http://0.0.0.0",
               help='Endpoint URL for DNSaaS.'),
    cfg.StrOpt('dns_service_type', default="",
               help='Service Type for DNSaaS.'),
    cfg.StrOpt('dns_region', default="",
               help='Region name for DNSaaS.'),
    cfg.URIOpt('dns_auth_url', default="http://0.0.0.0",
               help='Authentication URL for DNSaaS.'),
    cfg.StrOpt('dns_domain_name', default="",
               help='Domain name used for adding DNS entries.'),
    cfg.StrOpt('dns_username', default="", secret=True,
               help='Username for DNSaaS.'),
    cfg.StrOpt('dns_passkey', default="", secret=True,
               help='Passkey for DNSaaS.'),
    cfg.URIOpt('dns_management_base_url', default="http://0.0.0.0",
               help='Management URL for DNSaaS.'),
    cfg.IntOpt('dns_ttl', default=300,
               help='Time (in seconds) before a refresh of DNS information '
                    'occurs.'),
    cfg.StrOpt('dns_domain_id', default="",
               help='Domain ID used for adding DNS entries.'),
    cfg.IntOpt('users_page_size', default=20,
               help='Page size for listing users.'),
    cfg.IntOpt('databases_page_size', default=20,
               help='Page size for listing databases.'),
    cfg.IntOpt('instances_page_size', default=20,
               help='Page size for listing instances.'),
    cfg.IntOpt('clusters_page_size', default=20,
               help='Page size for listing clusters.'),
    cfg.IntOpt('backups_page_size', default=20,
               help='Page size for listing backups.'),
    cfg.IntOpt('configurations_page_size', default=20,
               help='Page size for listing configurations.'),
    cfg.IntOpt('modules_page_size', default=20,
               help='Page size for listing modules.'),
    cfg.IntOpt('agent_call_low_timeout', default=15,
               help="Maximum time (in seconds) to wait for Guest Agent 'quick'"
                    "requests (such as retrieving a list of users or "
                    "databases)."),
    cfg.IntOpt('agent_call_high_timeout', default=60 * 10,
               help="Maximum time (in seconds) to wait for Guest Agent 'slow' "
                    "requests (such as restarting the database)."),
    cfg.IntOpt('agent_replication_snapshot_timeout', default=36000,
               help='Maximum time (in seconds) to wait for taking a Guest '
                    'Agent replication snapshot.'),
    # The guest_id opt definition must match the one in cmd/guest.py
    cfg.StrOpt('guest_id', default=None, help="ID of the Guest Instance."),
    cfg.IntOpt('state_change_wait_time', default=60 * 10,
               help='Maximum time (in seconds) to wait for a state change.'),
    cfg.IntOpt('state_change_poll_time', default=3,
               help='Interval between state change poll requests (seconds).'),
    cfg.IntOpt('agent_heartbeat_time', default=10,
               help='Maximum time (in seconds) for the Guest Agent to reply '
                    'to a heartbeat request.'),
    cfg.IntOpt('agent_heartbeat_expiry', default=60,
               help='Time (in seconds) after which a guest is considered '
                    'unreachable'),
    cfg.IntOpt('num_tries', default=3,
               help='Number of times to check if a volume exists.'),
    cfg.StrOpt('volume_fstype', default='ext3',
               help='File system type used to format a volume.'),
    cfg.StrOpt('cinder_volume_type', default=None,
               help='Volume type to use when provisioning a Cinder volume.'),
    cfg.StrOpt('format_options', default='-m 5',
               help='Options to use when formatting a volume.'),
    cfg.IntOpt('volume_format_timeout', default=120,
               help='Maximum time (in seconds) to wait for a volume format.'),
    cfg.StrOpt('mount_options', default='defaults,noatime',
               help='Options to use when mounting a volume.'),
    cfg.IntOpt('max_instances_per_tenant',
               default=10,
               help='Default maximum number of instances per tenant.',
               deprecated_name='max_instances_per_user'),
    cfg.IntOpt('max_accepted_volume_size', default=10,
               help='Default maximum volume size (in GB) for an instance.'),
    cfg.IntOpt('max_volumes_per_tenant', default=40,
               help='Default maximum volume capacity (in GB) spanning across '
                    'all Trove volumes per tenant.',
               deprecated_name='max_volumes_per_user'),
    cfg.IntOpt('max_backups_per_tenant', default=50,
               help='Default maximum number of backups created by a tenant.',
               deprecated_name='max_backups_per_user'),
    cfg.StrOpt('quota_driver', default='trove.quota.quota.DbQuotaDriver',
               help='Default driver to use for quota checks.'),
    cfg.StrOpt('taskmanager_queue', default='taskmanager',
               help='Message queue name the Taskmanager will listen to.'),
    cfg.StrOpt('conductor_queue', default='trove-conductor',
               help='Message queue name the Conductor will listen on.'),
    cfg.IntOpt('trove_conductor_workers',
               help='Number of workers for the Conductor service. The default '
               'will be the number of CPUs available.'),
    cfg.BoolOpt('use_nova_server_config_drive', default=True,
                help='Use config drive for file injection when booting '
                'instance.'),
    cfg.BoolOpt('use_nova_server_volume', default=False,
                help='Whether to provision a Cinder volume for the '
                     'Nova instance.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('default_datastore', default=None,
               help='The default datastore id or name to use if one is not '
               'provided by the user. If the default value is None, the field '
               'becomes required in the instance create request.'),
    cfg.StrOpt('datastore_manager', default=None,
               help='Manager class in the Guest Agent, set up by the '
               'Taskmanager on instance provision.'),
    cfg.StrOpt('block_device_mapping', default='vdb',
               help='Block device to map onto the created instance.'),
    cfg.IntOpt('server_delete_time_out', default=60,
               help='Maximum time (in seconds) to wait for a server delete.'),
    cfg.IntOpt('volume_time_out', default=60,
               help='Maximum time (in seconds) to wait for a volume attach.'),
    cfg.IntOpt('reboot_time_out', default=60 * 2,
               help='Maximum time (in seconds) to wait for a server reboot.'),
    cfg.IntOpt('dns_time_out', default=60 * 2,
               help='Maximum time (in seconds) to wait for a DNS entry add.'),
    cfg.IntOpt('resize_time_out', default=60 * 15,
               help='Maximum time (in seconds) to wait for a server resize.'),
    cfg.IntOpt('revert_time_out', default=60 * 10,
               help='Maximum time (in seconds) to wait for a server resize '
                    'revert.'),
    cfg.IntOpt('cluster_delete_time_out', default=60 * 3,
               help='Maximum time (in seconds) to wait for a cluster delete.'),
    cfg.ListOpt('root_grant', default=['ALL'],
                help="Permissions to grant to the 'root' user."),
    cfg.BoolOpt('root_grant_option', default=True,
                help="Assign the 'root' user GRANT permissions."),
    cfg.IntOpt('http_get_rate', default=200,
               help="Maximum number of HTTP 'GET' requests (per minute)."),
    cfg.IntOpt('http_post_rate', default=200,
               help="Maximum number of HTTP 'POST' requests (per minute)."),
    cfg.IntOpt('http_delete_rate', default=200,
               help="Maximum number of HTTP 'DELETE' requests (per minute)."),
    cfg.IntOpt('http_put_rate', default=200,
               help="Maximum number of HTTP 'PUT' requests (per minute)."),
    cfg.IntOpt('http_mgmt_post_rate', default=200,
               help="Maximum number of management HTTP 'POST' requests "
                    "(per minute)."),
    cfg.BoolOpt('hostname_require_valid_ip', default=True,
                help='Require user hostnames to be valid IP addresses.',
                deprecated_name='hostname_require_ipv4'),
    cfg.BoolOpt('trove_security_groups_support', default=True,
                help='Whether Trove should add Security Groups on create.'),
    cfg.StrOpt('trove_security_group_name_prefix', default='SecGroup',
               help='Prefix to use when creating Security Groups.'),
    cfg.StrOpt('trove_security_group_rule_cidr', default='0.0.0.0/0',
               help='CIDR to use when creating Security Group Rules.'),
    cfg.IntOpt('trove_api_workers',
               help='Number of workers for the API service. The default will '
               'be the number of CPUs available.'),
    cfg.IntOpt('usage_sleep_time', default=5,
               help='Time to sleep during the check for an active Guest.'),
    cfg.StrOpt('region', default='LOCAL_DEV',
               help='The region this service is located.'),
    cfg.StrOpt('backup_runner',
               default='trove.guestagent.backup.backup_types.InnoBackupEx',
               help='Runner to use for backups.'),
    cfg.DictOpt('backup_runner_options', default={},
                help='Additional options to be passed to the backup runner.'),
    cfg.BoolOpt('verify_swift_checksum_on_restore', default=True,
                help='Enable verification of Swift checksum before starting '
                'restore. Makes sure the checksum of original backup matches '
                'the checksum of the Swift backup file.'),
    cfg.BoolOpt('verify_replica_volume_size', default=True,
                help='Require the replica volume size to be greater than '
                'or equal to the size of the master volume '
                'during replica creation.'),
    cfg.StrOpt('storage_strategy', default='SwiftStorage',
               help="Default strategy to store backups."),
    cfg.StrOpt('storage_namespace',
               default='trove.common.strategies.storage.swift',
               help='Namespace to load the default storage strategy from.'),
    cfg.StrOpt('backup_swift_container', default='database_backups',
               help='Swift container to put backups in.'),
    cfg.BoolOpt('backup_use_gzip_compression', default=True,
                help='Compress backups using gzip.'),
    cfg.BoolOpt('backup_use_openssl_encryption', default=True,
                help='Encrypt backups using OpenSSL.'),
    cfg.StrOpt('backup_aes_cbc_key', default='default_aes_cbc_key',
               help='Default OpenSSL aes_cbc key.'),
    cfg.BoolOpt('backup_use_snet', default=False,
                help='Send backup files over snet.'),
    cfg.IntOpt('backup_chunk_size', default=2 ** 16,
               help='Chunk size (in bytes) to stream to the Swift container. '
               'This should be in multiples of 128 bytes, since this is the '
               'size of an md5 digest block allowing the process to update '
               'the file checksum during streaming. '
               'See: http://stackoverflow.com/questions/1131220/'),
    cfg.IntOpt('backup_segment_max_size', default=2 * (1024 ** 3),
               help='Maximum size (in bytes) of each segment of the backup '
               'file.'),
    cfg.StrOpt('remote_dns_client',
               default='trove.common.remote.dns_client',
               help='Client to send DNS calls to.'),
    cfg.StrOpt('remote_guest_client',
               default='trove.common.remote.guest_client',
               help='Client to send Guest Agent calls to.'),
    cfg.StrOpt('remote_nova_client',
               default='trove.common.remote.nova_client',
               help='Client to send Nova calls to.'),
    cfg.StrOpt('remote_neutron_client',
               default='trove.common.remote.neutron_client',
               help='Client to send Neutron calls to.'),
    cfg.StrOpt('remote_cinder_client',
               default='trove.common.remote.cinder_client',
               help='Client to send Cinder calls to.'),
    cfg.StrOpt('remote_swift_client',
               default='trove.common.remote.swift_client',
               help='Client to send Swift calls to.'),
    cfg.StrOpt('remote_trove_client',
               default='trove.common.trove_remote.trove_client',
               help='Client to send Trove calls to.'),
    cfg.StrOpt('remote_glance_client',
               default='trove.common.glance_remote.glance_client',
               help='Client to send Glance calls to.'),
    cfg.StrOpt('exists_notification_transformer',
               help='Transformer for exists notifications.'),
    cfg.IntOpt('exists_notification_interval', default=3600,
               help='Seconds to wait between pushing events.'),
    cfg.IntOpt('quota_notification_interval',
               help='Seconds to wait between pushing events.'),
    cfg.DictOpt('notification_service_id',
                default={'mysql': '2f3ff068-2bfb-4f70-9a9d-a6bb65bc084b',
                         'percona': 'fd1723f5-68d2-409c-994f-a4a197892a17',
                         'pxc': '75a628c3-f81b-4ffb-b10a-4087c26bc854',
                         'redis': 'b216ffc5-1947-456c-a4cf-70f94c05f7d0',
                         'cassandra': '459a230d-4e97-4344-9067-2a54a310b0ed',
                         'couchbase': 'fa62fe68-74d9-4779-a24e-36f19602c415',
                         'mongodb': 'c8c907af-7375-456f-b929-b637ff9209ee',
                         'postgresql': 'ac277e0d-4f21-40aa-b347-1ea31e571720',
                         'couchdb': 'f0a9ab7b-66f7-4352-93d7-071521d44c7c',
                         'vertica': 'a8d805ae-a3b2-c4fd-gb23-b62cee5201ae',
                         'db2': 'e040cd37-263d-4869-aaa6-c62aa97523b5',
                         'mariadb': '7a4f82cc-10d2-4bc6-aadc-d9aacc2a3cb5'},
                help='Unique ID to tag notification events.'),
    cfg.StrOpt('nova_proxy_admin_user', default='',
               help="Admin username used to connect to Nova.", secret=True),
    cfg.StrOpt('nova_proxy_admin_pass', default='',
               help="Admin password used to connect to Nova.", secret=True),
    cfg.StrOpt('nova_proxy_admin_tenant_id', default='',
               help="Admin tenant ID used to connect to Nova.", secret=True),
    cfg.StrOpt('nova_proxy_admin_tenant_name', default='',
               help="Admin tenant name used to connect to Nova.", secret=True),
    cfg.StrOpt('network_label_regex', default='^private$',
               help='Regular expression to match Trove network labels.'),
    cfg.StrOpt('ip_regex', default=None,
               help='List IP addresses that match this regular expression.'),
    cfg.StrOpt('black_list_regex', default=None,
               help='Exclude IP addresses that match this regular '
                    'expression.'),
    cfg.StrOpt('cloudinit_location', default='/etc/trove/cloudinit',
               help='Path to folder with cloudinit scripts.'),
    cfg.StrOpt('injected_config_location', default='/etc/trove/conf.d',
               help='Path to folder on the Guest where config files will be '
                    'injected during instance creation.'),
    cfg.StrOpt('guest_config',
               default='/etc/trove/trove-guestagent.conf',
               help='Path to the Guest Agent config file to be injected '
                    'during instance creation.'),
    cfg.StrOpt('guest_info',
               default='guest_info.conf',
               help='The guest info filename found in the injected config '
                    'location.  If a full path is specified then it will '
                    'be used as the path to the guest info file'),
    cfg.DictOpt('datastore_registry_ext', default=dict(),
                help='Extension for default datastore managers. '
                     'Allows the use of custom managers for each of '
                     'the datastores supported by Trove.'),
    cfg.StrOpt('template_path', default='/etc/trove/templates/',
               help='Path which leads to datastore templates.'),
    cfg.BoolOpt('sql_query_logging', default=False,
                help='Allow insecure logging while '
                     'executing queries through SQLAlchemy.'),
    cfg.ListOpt('expected_filetype_suffixes', default=['json'],
                help='Filetype endings not to be reattached to an ID '
                     'by the utils method correct_id_with_req.'),
    cfg.ListOpt('default_neutron_networks', default=[],
                help='List of IDs for management networks which should be '
                     'attached to the instance regardless of what NICs '
                     'are specified in the create API call.'),
    cfg.IntOpt('max_header_line', default=16384,
               help='Maximum line size of message headers to be accepted. '
                    'max_header_line may need to be increased when using '
                    'large tokens (typically those generated by the '
                    'Keystone v3 API with big service catalogs).'),
    cfg.StrOpt('conductor_manager', default='trove.conductor.manager.Manager',
               help='Qualified class name to use for conductor manager.'),
    cfg.StrOpt('network_driver', default='trove.network.nova.NovaNetwork',
               help="Describes the actual network manager used for "
                    "the management of network attributes "
                    "(security groups, floating IPs, etc.)."),
    cfg.IntOpt('usage_timeout', default=60 * 30,
               help='Maximum time (in seconds) to wait for a Guest to become '
                    'active.'),
    cfg.IntOpt('restore_usage_timeout', default=36000,
               help='Maximum time (in seconds) to wait for a Guest instance '
                    'restored from a backup to become active.'),
    cfg.IntOpt('cluster_usage_timeout', default=36000,
               help='Maximum time (in seconds) to wait for a cluster to '
                    'become active.'),
    cfg.IntOpt('timeout_wait_for_service', default=120,
               help='Maximum time (in seconds) to wait for a service to '
                    'become alive.'),
    cfg.StrOpt('module_aes_cbc_key', default='module_aes_cbc_key',
               help='OpenSSL aes_cbc key for module encryption.'),
    cfg.ListOpt('module_types', default=['ping', 'new_relic_license'],
                help='A list of module types supported. A module type '
                     'corresponds to the name of a ModuleDriver.'),
    cfg.IntOpt('module_reapply_max_batch_size', default=50,
               help='The maximum number of instances to reapply a module to '
                    'at the same time.'),
    cfg.IntOpt('module_reapply_min_batch_delay', default=2,
               help='The minimum delay (in seconds) between subsequent '
                    'module batch reapply executions.'),
    cfg.StrOpt('guest_log_container_name',
               default='database_logs',
               help='Name of container that stores guest log components.'),
    cfg.IntOpt('guest_log_limit', default=1000000,
               help='Maximum size of a chunk saved in guest log container.'),
    cfg.IntOpt('guest_log_expiry', default=2592000,
               help='Expiry (in seconds) of objects in guest log container.'),
    cfg.BoolOpt('enable_secure_rpc_messaging', default=True,
                help='Should RPC messaging traffic be secured by encryption.'),
    cfg.StrOpt('taskmanager_rpc_encr_key',
               default='bzH6y0SGmjuoY0FNSTptrhgieGXNDX6PIhvz',
               help='Key (OpenSSL aes_cbc) for taskmanager RPC encryption.'),
    cfg.StrOpt('inst_rpc_key_encr_key',
               default='emYjgHFqfXNB1NGehAFIUeoyw4V4XwWHEaKP',
               help='Key (OpenSSL aes_cbc) to encrypt instance keys in DB.'),
    cfg.StrOpt('instance_rpc_encr_key',
               help='Key (OpenSSL aes_cbc) for instance RPC encryption.'),
]


database_opts = [
    cfg.StrOpt('connection',
               default='sqlite:///trove_test.sqlite',
               help='SQL Connection.',
               secret=True,
               deprecated_name='sql_connection',
               deprecated_group='DEFAULT'),
    cfg.IntOpt('idle_timeout',
               default=3600,
               deprecated_name='sql_idle_timeout',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('query_log',
                default=False,
                deprecated_name='sql_query_log',
                deprecated_group='DEFAULT',
                deprecated_for_removal=True),
    cfg.BoolOpt('sqlite_synchronous',
                default=True,
                help='If True, SQLite uses synchronous mode.'),
    cfg.StrOpt('slave_connection',
               secret=True,
               help='The SQLAlchemy connection string to use to connect to the'
                    ' slave database.'),
    cfg.StrOpt('mysql_sql_mode',
               default='TRADITIONAL',
               help='The SQL mode to be used for MySQL sessions. '
                    'This option, including the default, overrides any '
                    'server-set SQL mode. To use whatever SQL mode '
                    'is set by the server configuration, '
                    'set this to no value. Example: mysql_sql_mode='),
    cfg.IntOpt('max_pool_size',
               help='Maximum number of SQL connections to keep open in a '
                    'pool.'),
    cfg.IntOpt('max_retries',
               default=10,
               help='Maximum number of database connection retries '
                    'during startup. Set to -1 to specify an infinite '
                    'retry count.'),
    cfg.IntOpt('retry_interval',
               default=10,
               help='Interval between retries of opening a SQL connection.'),
    cfg.IntOpt('max_overflow',
               help='If set, use this value for max_overflow with '
                    'SQLAlchemy.'),
    cfg.IntOpt('connection_debug',
               default=0,
               help='Verbosity of SQL debugging information: 0=None, '
                    '100=Everything.'),
    cfg.BoolOpt('connection_trace',
                default=False,
                help='Add Python stack traces to SQL as comment strings.'),
    cfg.IntOpt('pool_timeout',
               help='If set, use this value for pool_timeout with '
                    'SQLAlchemy.'),
]


# Datastore specific option groups

# Mysql
mysql_group = cfg.OptGroup(
    'mysql', title='MySQL options',
    help="Oslo option group designed for MySQL datastore")
mysql_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["3306"], item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default='MysqlGTIDReplication',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.mysql_gtid',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=400,
               help='Maximum time (in seconds) to wait for a Guest to become '
                    'active.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.mysql_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.mysql_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'InnoBackupEx': 'InnoBackupExIncremental'},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental backup, the runner will use the default full '
                'backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.mysql.service.MySQLRootController',
               help='Root controller implementation for mysql.'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root'],
                help='Users to exclude when listing users.',
                deprecated_name='ignore_users',
                deprecated_group='DEFAULT'),
    cfg.ListOpt('ignore_dbs',
                default=['mysql', 'information_schema', 'performance_schema'],
                help='Databases to exclude when listing databases.',
                deprecated_name='ignore_dbs',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('guest_log_exposed_logs', default='general,slow_query',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('guest_log_long_query_time', default=1000,
               help='The time in milliseconds that a statement must take in '
                    'in order to be logged in the slow_query log.',
               deprecated_for_removal=True,
               deprecated_reason='Will be replaced by a configuration group '
               'option: long_query_time'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# Percona
percona_group = cfg.OptGroup(
    'percona', title='Percona options',
    help="Oslo option group designed for Percona datastore")
percona_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["3306"], item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default='MysqlGTIDReplication',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.mysql_gtid',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('replication_user', default='slave_user',
               help='Userid for replication slave.'),
    cfg.StrOpt('replication_password', default='NETOU7897NNLOU',
               help='Password for replication slave user.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Maximum time (in seconds) to wait for a Guest to become '
                    'active.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.mysql_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.mysql_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'InnoBackupEx': 'InnoBackupExIncremental'},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental backup, the runner will use the default full '
                'backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for percona.'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root'],
                help='Users to exclude when listing users.',
                deprecated_name='ignore_users',
                deprecated_group='DEFAULT'),
    cfg.ListOpt('ignore_dbs',
                default=['mysql', 'information_schema', 'performance_schema'],
                help='Databases to exclude when listing databases.',
                deprecated_name='ignore_dbs',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('guest_log_exposed_logs', default='general,slow_query',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('guest_log_long_query_time', default=1000,
               help='The time in milliseconds that a statement must take in '
                    'in order to be logged in the slow_query log.',
               deprecated_for_removal=True,
               deprecated_reason='Will be replaced by a configuration group '
               'option: long_query_time'),
    cfg.IntOpt('default_password_length',
               default='${mysql.default_password_length}',
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# Percona XtraDB Cluster
pxc_group = cfg.OptGroup(
    'pxc', title='Percona XtraDB Cluster options',
    help="Oslo option group designed for Percona XtraDB Cluster datastore")
pxc_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["3306", "4444", "4567", "4568"],
                item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('replication_strategy', default='MysqlGTIDReplication',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.mysql_gtid',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('replication_user', default='slave_user',
               help='Userid for replication slave.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Maximum time (in seconds) to wait for a Guest to become '
                    'active.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.mysql_impl',
               help='Namespace to load backup strategies from.'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.mysql_impl',
               help='Namespace to load restore strategies from.'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'InnoBackupEx': 'InnoBackupExIncremental'},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental backup, the runner will use the default full '
                'backup.'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root', 'clusterrepuser'],
                help='Users to exclude when listing users.'),
    cfg.ListOpt('ignore_dbs',
                default=['mysql', 'information_schema', 'performance_schema'],
                help='Databases to exclude when listing databases.'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.IntOpt('min_cluster_member_count', default=3,
               help='Minimum number of members in PXC cluster.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.api.GaleraCommonAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.taskmanager.GaleraCommonTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.guestagent.GaleraCommonGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.pxc.service.PxcRootController',
               help='Root controller implementation for pxc.'),
    cfg.StrOpt('guest_log_exposed_logs', default='general,slow_query',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('guest_log_long_query_time', default=1000,
               help='The time in milliseconds that a statement must take in '
                    'in order to be logged in the slow_query log.',
               deprecated_for_removal=True,
               deprecated_reason='Will be replaced by a configuration group '
               'option: long_query_time'),
    cfg.IntOpt('default_password_length',
               default='${mysql.default_password_length}',
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]


# Redis
redis_group = cfg.OptGroup(
    'redis', title='Redis options',
    help="Oslo option group designed for Redis datastore")
redis_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["6379", "16379"],
                item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='RedisBackup',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default='RedisSyncReplication',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.experimental.'
                       'redis_sync',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('mount_point', default='/var/lib/redis',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('backup_namespace',
               default="trove.guestagent.strategies.backup.experimental."
                       "redis_impl",
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default="trove.guestagent.strategies.restore.experimental."
                       "redis_impl",
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'redis.api.RedisAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental.redis.'
               'taskmanager.RedisTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'redis.guestagent.RedisGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for redis.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# Cassandra
cassandra_group = cfg.OptGroup(
    'cassandra', title='Cassandra options',
    help="Oslo option group designed for Cassandra datastore")
cassandra_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["7000", "7001", "7199", "9042", "9160"],
                item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental strategy based on the default backup '
                'strategy. For strategies that do not implement incremental '
                'backups, the runner performs full backup instead.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('backup_strategy', default="NodetoolSnapshot",
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.StrOpt('mount_point', default='/var/lib/cassandra',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('backup_namespace',
               default="trove.guestagent.strategies.backup.experimental."
               "cassandra_impl",
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default="trove.guestagent.strategies.restore.experimental."
               "cassandra_impl",
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.cassandra.service'
               '.CassandraRootController',
               help='Root controller implementation for Cassandra.'),
    cfg.ListOpt('ignore_users', default=['os_admin'],
                help='Users to exclude when listing users.'),
    cfg.ListOpt('ignore_dbs', default=['system', 'system_auth',
                                       'system_traces'],
                help='Databases to exclude when listing databases.'),
    cfg.StrOpt('guest_log_exposed_logs', default='system',
               help='List of Guest Logs to expose for publishing.'),
    cfg.StrOpt('system_log_level',
               choices=['ALL', 'TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'],
               default='INFO',
               help='Cassandra log verbosity.'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'cassandra.api.CassandraAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental'
               '.cassandra.taskmanager.CassandraTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental'
               '.cassandra.guestagent.CassandraGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('enable_cluster_instance_backup',
                default=False,
                help='Allows backup of single instance in the cluster.'),
    cfg.BoolOpt('enable_saslauthd', default=False,
                help='Enable the saslauth daemon.'),
    cfg.StrOpt('user_controller',
               default='trove.extensions.cassandra.service.'
               'CassandraUserController',
               help='User controller implementation.'),
    cfg.StrOpt('database_controller',
               default='trove.extensions.cassandra.service.'
               'CassandraDatabaseController',
               help='Database controller implementation.'),
    cfg.StrOpt('user_access_controller',
               default='trove.extensions.cassandra.service.'
               'CassandraUserAccessController',
               help='User access controller implementation.'),
    cfg.IntOpt('node_sync_time', default=60,
               help='Time (in seconds) given to a node after a state change '
               'to finish rejoining the cluster.'),
]

# Couchbase
couchbase_group = cfg.OptGroup(
    'couchbase', title='Couchbase options',
    help="Oslo option group designed for Couchbase datastore")
couchbase_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', item_type=ListOfPortsType,
                default=["8091", "8092", "4369", "11209-11211",
                         "21100-21199"],
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='CbBackup',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.StrOpt('mount_point', default='/var/lib/couchbase',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.experimental.'
               'couchbase_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.experimental.'
               'couchbase_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for couchbase.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('default_password_length', default=24, min=6, max=24,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# MongoDB
mongodb_group = cfg.OptGroup(
    'mongodb', title='MongoDB options',
    help="Oslo option group designed for MongoDB datastore")
mongodb_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["2500", "27017", "27019"],
                item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='MongoDump',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.StrOpt('mount_point', default='/var/lib/mongodb',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.IntOpt('num_config_servers_per_cluster', default=3,
               help='The number of config servers to create per cluster.'),
    cfg.IntOpt('num_query_routers_per_cluster', default=1,
               help='The number of query routers (mongos) to create '
                    'per cluster.'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.BoolOpt('cluster_secure', default=True,
                help='Create secure clusters. If False then the '
                     'Role-Based Access Control will be disabled.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'mongodb.api.MongoDbAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental.mongodb.'
               'taskmanager.MongoDbTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'mongodb.guestagent.MongoDbGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.experimental.'
                       'mongo_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.experimental.'
                       'mongo_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.PortOpt('mongodb_port', default=27017,
                help='Port for mongod and mongos instances.'),
    cfg.PortOpt('configsvr_port', default=27019,
                help='Port for instances running as config servers.'),
    cfg.ListOpt('ignore_dbs', default=['admin', 'local', 'config'],
                help='Databases to exclude when listing databases.'),
    cfg.ListOpt('ignore_users', default=['admin.os_admin', 'admin.root'],
                help='Users to exclude when listing users.'),
    cfg.IntOpt('add_members_timeout', default=300,
               help='Maximum time to wait (in seconds) for a replica set '
                    'initialization process to complete.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.mongodb.service.'
                       'MongoDBRootController',
               help='Root controller implementation for mongodb.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# PostgreSQL
postgresql_group = cfg.OptGroup(
    'postgresql', title='PostgreSQL options',
    help="Oslo option group for the PostgreSQL datastore.")
postgresql_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["5432"], item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.PortOpt('postgresql_port', default=5432,
                help='The TCP port the server listens on.'),
    cfg.StrOpt('backup_strategy', default='PgBaseBackup',
               help='Default strategy to perform backups.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'PgBaseBackup': 'PgBaseBackupIncremental'},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.'),
    cfg.StrOpt('replication_strategy',
               default='PostgresqlReplicationStreaming',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.experimental.'
                       'postgresql_impl',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('mount_point', default='/var/lib/postgresql',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.StrOpt('wal_archive_location', default='/mnt/wal_archive',
               help="Filesystem path storing WAL archive files when "
                    "WAL-shipping based backups or replication "
                    "is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.experimental.'
               'postgresql_impl',
               help='Namespace to load backup strategies from.'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.experimental.'
               'postgresql_impl',
               help='Namespace to load restore strategies from.'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'postgres', 'root']),
    cfg.ListOpt('ignore_dbs', default=['os_admin', 'postgres']),
    cfg.StrOpt('root_controller',
               default='trove.extensions.postgresql.service'
               '.PostgreSQLRootController',
               help='Root controller implementation for postgresql.'),
    cfg.StrOpt('guest_log_exposed_logs', default='general',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('guest_log_long_query_time', default=0,
               help="The time in milliseconds that a statement must take in "
                    "in order to be logged in the 'general' log.  A value of "
                    "'0' logs all statements, while '-1' turns off "
                    "statement logging.",
               deprecated_for_removal=True,
               deprecated_reason='Will be replaced by configuration group '
               'option: log_min_duration_statement'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# Apache CouchDB
couchdb_group = cfg.OptGroup(
    'couchdb', title='CouchDB options',
    help="Oslo option group designed for CouchDB datastore")
couchdb_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports',
                default=["5984"], item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('mount_point', default='/var/lib/couchdb',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('backup_strategy', default='CouchDBBackup',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.StrOpt('backup_namespace', default='trove.guestagent.strategies'
               '.backup.experimental.couchdb_impl',
               help='Namespace to load backup strategies from.'),
    cfg.StrOpt('restore_namespace', default='trove.guestagent.strategies'
               '.restore.experimental.couchdb_impl',
               help='Namespace to load restore strategies from.'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.'),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                'instance-create as the "password" field.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for couchdb.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root'],
                help='Users to exclude when listing users.',
                deprecated_name='ignore_users',
                deprecated_group='DEFAULT'),
    cfg.ListOpt('ignore_dbs',
                default=['_users', '_replicator'],
                help='Databases to exclude when listing databases.',
                deprecated_name='ignore_dbs',
                deprecated_group='DEFAULT'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# Vertica
vertica_group = cfg.OptGroup(
    'vertica', title='Vertica options',
    help="Oslo option group designed for Vertica datastore")
vertica_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', item_type=ListOfPortsType,
                default=["5433", "5434", "22", "5444", "5450", "4803"],
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', item_type=ListOfPortsType,
                default=["5433", "4803", "4804", "6453"],
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default=None,
               help='Default strategy to perform backups.'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.StrOpt('mount_point', default='/var/lib/vertica',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('backup_namespace', default=None,
               help='Namespace to load backup strategies from.'),
    cfg.StrOpt('restore_namespace', default=None,
               help='Namespace to load restore strategies from.'),
    cfg.IntOpt('readahead_size', default=2048,
               help='Size(MB) to be set as readahead_size for data volume'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.IntOpt('cluster_member_count', default=3,
               help='Number of members in Vertica cluster.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.vertica.'
                       'api.VerticaAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental.vertica.'
                       'taskmanager.VerticaTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental.vertica.'
                       'guestagent.VerticaGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.vertica.service.'
                       'VerticaRootController',
               help='Root controller implementation for Vertica.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('min_ksafety', default=0,
               help='Minimum k-safety setting permitted for vertica clusters'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# DB2
db2_group = cfg.OptGroup(
    'db2', title='DB2 options',
    help="Oslo option group designed for DB2 datastore")
db2_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports',
                default=["50000"], item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                'in the security group (only applicable '
                'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                'in the security group (only applicable '
                'if trove_security_groups_support is True).'),
    cfg.StrOpt('mount_point', default="/home/db2inst1/db2inst1",
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.StrOpt('backup_strategy', default='DB2OfflineBackup',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('replication_strategy', default=None,
               help='Default strategy for replication.'),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.experimental.'
                       'db2_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.experimental.'
                       'db2_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.DictOpt('backup_incremental_strategy', default={},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental, the runner will use the default full backup.'),
    cfg.ListOpt('ignore_users', default=['PUBLIC', 'DB2INST1']),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for db2.'),
    cfg.StrOpt('guest_log_exposed_logs', default='',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('default_password_length', default=36,
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# MariaDB
mariadb_group = cfg.OptGroup(
    'mariadb', title='MariaDB options',
    help="Oslo option group designed for MariaDB datastore")
mariadb_opts = [
    cfg.BoolOpt('icmp', default=False,
                help='Whether to permit ICMP.'),
    cfg.ListOpt('tcp_ports', default=["3306", "4444", "4567", "4568"],
                item_type=ListOfPortsType,
                help='List of TCP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[], item_type=ListOfPortsType,
                help='List of UDP ports and/or port ranges to open '
                     'in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='MariaDBInnoBackupEx',
               help='Default strategy to perform backups.',
               deprecated_name='backup_strategy',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('replication_strategy', default='MariaDBGTIDReplication',
               help='Default strategy for replication.'),
    cfg.StrOpt('replication_namespace',
               default='trove.guestagent.strategies.replication.experimental'
               '.mariadb_gtid',
               help='Namespace to load replication strategies from.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=400,
               help='Maximum time (in seconds) to wait for a Guest to become '
                    'active.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.experimental'
                       '.mariadb_impl',
               help='Namespace to load backup strategies from.',
               deprecated_name='backup_namespace',
               deprecated_group='DEFAULT'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.experimental'
                       '.mariadb_impl',
               help='Namespace to load restore strategies from.',
               deprecated_name='restore_namespace',
               deprecated_group='DEFAULT'),
    cfg.BoolOpt('volume_support', default=True,
                help='Whether to provision a Cinder volume for datadir.'),
    cfg.StrOpt('device_path', default='/dev/vdb',
               help='Device path for volume if volume support is enabled.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'MariaDBInnoBackupEx':
                         'MariaDBInnoBackupExIncremental'},
                help='Incremental Backup Runner based on the default '
                'strategy. For strategies that do not implement an '
                'incremental backup, the runner will use the default full '
                'backup.',
                deprecated_name='backup_incremental_strategy',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('root_controller',
               default='trove.extensions.common.service.DefaultRootController',
               help='Root controller implementation for mysql.'),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root'],
                help='Users to exclude when listing users.',
                deprecated_name='ignore_users',
                deprecated_group='DEFAULT'),
    cfg.ListOpt('ignore_dbs',
                default=['mysql', 'information_schema', 'performance_schema'],
                help='Databases to exclude when listing databases.',
                deprecated_name='ignore_dbs',
                deprecated_group='DEFAULT'),
    cfg.StrOpt('guest_log_exposed_logs', default='general,slow_query',
               help='List of Guest Logs to expose for publishing.'),
    cfg.IntOpt('guest_log_long_query_time', default=1000,
               help='The time in milliseconds that a statement must take in '
                    'in order to be logged in the slow_query log.',
               deprecated_for_removal=True,
               deprecated_reason='Will be replaced by a configuration group '
               'option: long_query_time'),
    cfg.BoolOpt('cluster_support', default=True,
                help='Enable clusters to be created and managed.'),
    cfg.IntOpt('min_cluster_member_count', default=3,
               help='Minimum number of members in MariaDB cluster.'),
    cfg.StrOpt('api_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.api.GaleraCommonAPIStrategy',
               help='Class that implements datastore-specific API logic.'),
    cfg.StrOpt('taskmanager_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.taskmanager.GaleraCommonTaskManagerStrategy',
               help='Class that implements datastore-specific task manager '
                    'logic.'),
    cfg.StrOpt('guestagent_strategy',
               default='trove.common.strategies.cluster.experimental.'
               'galera_common.guestagent.GaleraCommonGuestAgentStrategy',
               help='Class that implements datastore-specific Guest Agent API '
                    'logic.'),
    cfg.IntOpt('default_password_length',
               default='${mysql.default_password_length}',
               help='Character length of generated passwords.',
               deprecated_name='default_password_length',
               deprecated_group='DEFAULT'),
]

# RPC version groups
upgrade_levels = cfg.OptGroup(
    'upgrade_levels',
    title='RPC upgrade levels group for handling versions',
    help='Contains the support version caps (Openstack Release) for '
    'each RPC API')

rpcapi_cap_opts = [
    cfg.StrOpt(
        'taskmanager', default='latest',
        help='Set a version cap for messages sent to taskmanager services'),
    cfg.StrOpt(
        'guestagent', default='latest',
        help='Set a version cap for messages sent to guestagent services'),
    cfg.StrOpt(
        'conductor', default='latest',
        help='Set Openstack Release compatibility for conductor services'),
]

CONF = cfg.CONF

CONF.register_opts(path_opts)
CONF.register_opts(common_opts)

CONF.register_opts(database_opts, 'database')

CONF.register_group(mysql_group)
CONF.register_group(percona_group)
CONF.register_group(pxc_group)
CONF.register_group(redis_group)
CONF.register_group(cassandra_group)
CONF.register_group(couchbase_group)
CONF.register_group(mongodb_group)
CONF.register_group(postgresql_group)
CONF.register_group(couchdb_group)
CONF.register_group(vertica_group)
CONF.register_group(db2_group)
CONF.register_group(mariadb_group)

CONF.register_opts(mysql_opts, mysql_group)
CONF.register_opts(percona_opts, percona_group)
CONF.register_opts(pxc_opts, pxc_group)
CONF.register_opts(redis_opts, redis_group)
CONF.register_opts(cassandra_opts, cassandra_group)
CONF.register_opts(couchbase_opts, couchbase_group)
CONF.register_opts(mongodb_opts, mongodb_group)
CONF.register_opts(postgresql_opts, postgresql_group)
CONF.register_opts(couchdb_opts, couchdb_group)
CONF.register_opts(vertica_opts, vertica_group)
CONF.register_opts(db2_opts, db2_group)
CONF.register_opts(mariadb_opts, mariadb_group)

CONF.register_opts(rpcapi_cap_opts, upgrade_levels)

profiler.set_defaults(CONF)
logging.register_options(CONF)


def custom_parser(parsername, parser):
    CONF.register_cli_opt(cfg.SubCommandOpt(parsername, handler=parser))


def parse_args(argv, default_config_files=None):
    cfg.CONF(args=argv[1:],
             project='trove',
             version=version.cached_version_string(),
             default_config_files=default_config_files)


def get_ignored_dbs():
    try:
        return get_configuration_property('ignore_dbs')
    except NoSuchOptError:
        return []


def get_ignored_users():
    try:
        return get_configuration_property('ignore_users')
    except NoSuchOptError:
        return []


def get_configuration_property(property_name):
    """
    Get a configuration property.
    Try to get it from the datastore-specific section first.
    If it is not available, retrieve it from the DEFAULT section.
    """

    # Fake-integration tests do not define 'CONF.datastore_manager'.
    # *MySQL* options will
    # be loaded. This should never occur in a production environment.
    datastore_manager = CONF.datastore_manager
    if not datastore_manager:
        datastore_manager = 'mysql'
        LOG.warning(_("Manager name ('datastore_manager') not defined, "
                      "using '%s' options instead."), datastore_manager)

    try:
        return CONF.get(datastore_manager).get(property_name)
    except NoSuchOptError:
        return CONF.get(property_name)


def set_api_config_defaults():
    """This method updates all configuration default values."""

    cors.set_defaults(
        allow_headers=['X-Auth-Token',
                       'X-Identity-Status',
                       'X-Roles',
                       'X-Service-Catalog',
                       'X-User-Id',
                       'X-Tenant-Id',
                       'X-OpenStack-Request-ID'],
        expose_headers=['X-Auth-Token',
                        'X-Subject-Token',
                        'X-Service-Token',
                        'X-OpenStack-Request-ID'],
        allow_methods=['GET',
                       'PUT',
                       'POST',
                       'DELETE',
                       'PATCH']
    )
