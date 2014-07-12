# Copyright 2011 OpenStack Foundation
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

from oslo.config import cfg

import os.path

UNKNOWN_SERVICE_ID = 'unknown-service-id-error'

path_opts = [
    cfg.StrOpt('pybasedir',
               default=os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                    '../')),
               help='Directory where the trove python module is installed.'),
]

common_opts = [
    cfg.StrOpt('sql_connection',
               default='sqlite:///trove_test.sqlite',
               help='SQL Connection.',
               secret=True),
    cfg.IntOpt('sql_idle_timeout', default=3600),
    cfg.BoolOpt('sql_query_log', default=False),
    cfg.IntOpt('bind_port', default=8779),
    cfg.StrOpt('api_extensions_path', default='$pybasedir/extensions/routes',
               help='Path to extensions.'),
    cfg.StrOpt('api_paste_config',
               default="api-paste.ini",
               help='File name for the paste.deploy config for trove-api.'),
    cfg.BoolOpt('trove_volume_support',
                default=True,
                help='Whether to provision a cinder volume for datadir.'),
    cfg.ListOpt('admin_roles', default=['admin']),
    cfg.BoolOpt('update_status_on_fail', default=True,
                help='Set the service and instance task statuses to ERROR '
                     'when an instance fails to become active within the '
                     'configured usage_timeout.'),
    cfg.StrOpt('os_region_name',
               help='Region name of this node. Used when searching catalog.'),
    cfg.StrOpt('nova_compute_url', help='URL without the tenant segment.'),
    cfg.StrOpt('nova_compute_service_type', default='compute',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('cinder_url', help='URL without the tenant segment.'),
    cfg.StrOpt('cinder_service_type', default='volumev2',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('heat_url', help='URL without the tenant segment.'),
    cfg.StrOpt('heat_service_type', default='orchestration',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('swift_url', help='URL ending in AUTH_.'),
    cfg.StrOpt('swift_service_type', default='object-store',
               help='Service type to use when searching catalog.'),
    cfg.StrOpt('trove_auth_url', default='http://0.0.0.0:5000/v2.0'),
    cfg.StrOpt('host', default='0.0.0.0'),
    cfg.IntOpt('report_interval', default=10,
               help='The interval in seconds which periodic tasks are run.'),
    cfg.IntOpt('periodic_interval', default=60),
    cfg.BoolOpt('trove_dns_support', default=False),
    cfg.StrOpt('db_api_implementation', default='trove.db.sqlalchemy.api'),
    cfg.StrOpt('dns_driver', default='trove.dns.driver.DnsDriver'),
    cfg.StrOpt('dns_instance_entry_factory',
               default='trove.dns.driver.DnsInstanceEntryFactory'),
    cfg.StrOpt('dns_hostname', default=""),
    cfg.StrOpt('dns_account_id', default=""),
    cfg.StrOpt('dns_endpoint_url', default="0.0.0.0"),
    cfg.StrOpt('dns_service_type', default=""),
    cfg.StrOpt('dns_region', default=""),
    cfg.StrOpt('dns_auth_url', default=""),
    cfg.StrOpt('dns_domain_name', default=""),
    cfg.StrOpt('dns_username', default="", secret=True),
    cfg.StrOpt('dns_passkey', default="", secret=True),
    cfg.StrOpt('dns_management_base_url', default=""),
    cfg.IntOpt('dns_ttl', default=300),
    cfg.StrOpt('dns_domain_id', default=""),
    cfg.IntOpt('users_page_size', default=20),
    cfg.IntOpt('databases_page_size', default=20),
    cfg.IntOpt('instances_page_size', default=20),
    cfg.IntOpt('backups_page_size', default=20),
    cfg.IntOpt('configurations_page_size', default=20),
    cfg.ListOpt('ignore_users', default=['os_admin', 'root']),
    cfg.ListOpt('ignore_dbs', default=['lost+found',
                                       'mysql',
                                       'information_schema']),
    cfg.IntOpt('agent_call_low_timeout', default=5),
    cfg.IntOpt('agent_call_high_timeout', default=60),
    cfg.StrOpt('guest_id', default=None),
    cfg.IntOpt('state_change_wait_time', default=3 * 60),
    cfg.IntOpt('agent_heartbeat_time', default=10),
    cfg.IntOpt('num_tries', default=3),
    cfg.StrOpt('volume_fstype', default='ext3'),
    cfg.StrOpt('cinder_volume_type', default=None,
               help='Volume type to use when provisioning a cinder volume.'),
    cfg.StrOpt('format_options', default='-m 5'),
    cfg.IntOpt('volume_format_timeout', default=120),
    cfg.StrOpt('mount_options', default='defaults,noatime'),
    cfg.IntOpt('max_instances_per_user', default=5,
               help='Default maximum number of instances per tenant.'),
    cfg.IntOpt('max_accepted_volume_size', default=5,
               help='Default maximum volume size for an instance.'),
    cfg.IntOpt('max_volumes_per_user', default=20,
               help='Default maximum volume capacity (in GB) spanning across '
                    'all trove volumes per tenant.'),
    cfg.IntOpt('max_backups_per_user', default=50,
               help='Default maximum number of backups created by a tenant.'),
    cfg.StrOpt('quota_driver',
               default='trove.quota.quota.DbQuotaDriver',
               help='Default driver to use for quota checks.'),
    cfg.StrOpt('taskmanager_queue', default='taskmanager'),
    cfg.StrOpt('conductor_queue', default='trove-conductor'),
    cfg.IntOpt('trove_conductor_workers',
               help="Number of workers for the Conductor service. The default "
               "will be the number of CPUs available."),
    cfg.BoolOpt('use_nova_server_volume', default=False),
    cfg.BoolOpt('use_heat', default=False),
    cfg.StrOpt('device_path', default='/dev/vdb'),
    cfg.StrOpt('default_datastore', default=None,
               help="The default datastore id or name to use if one is not "
               "provided by the user. If the default value is None, the field "
               "becomes required in the instance-create request."),
    cfg.StrOpt('datastore_manager', default=None,
               help='Manager class in guestagent, setup by taskmanager on '
               'instance provision.'),
    cfg.StrOpt('block_device_mapping', default='vdb'),
    cfg.IntOpt('server_delete_time_out', default=60),
    cfg.IntOpt('volume_time_out', default=60),
    cfg.IntOpt('heat_time_out', default=60),
    cfg.IntOpt('reboot_time_out', default=60 * 2),
    cfg.IntOpt('dns_time_out', default=60 * 2),
    cfg.IntOpt('resize_time_out', default=60 * 10),
    cfg.IntOpt('revert_time_out', default=60 * 10),
    cfg.ListOpt('root_grant', default=['ALL']),
    cfg.BoolOpt('root_grant_option', default=True),
    cfg.IntOpt('default_password_length', default=36),
    cfg.IntOpt('http_get_rate', default=200),
    cfg.IntOpt('http_post_rate', default=200),
    cfg.IntOpt('http_delete_rate', default=200),
    cfg.IntOpt('http_put_rate', default=200),
    cfg.IntOpt('http_mgmt_post_rate', default=200),
    cfg.BoolOpt('hostname_require_ipv4', default=True,
                help="Require user hostnames to be IPv4 addresses."),
    cfg.BoolOpt('trove_security_groups_support', default=True),
    cfg.StrOpt('trove_security_group_name_prefix', default='SecGroup'),
    cfg.StrOpt('trove_security_group_rule_cidr', default='0.0.0.0/0'),
    cfg.IntOpt('trove_api_workers',
               help="Number of workers for the API service. The default will "
               "be the number of CPUs available."),
    cfg.IntOpt('usage_sleep_time', default=5,
               help='Time to sleep during the check active guest.'),
    cfg.StrOpt('region', default='LOCAL_DEV',
               help='The region this service is located.'),
    cfg.StrOpt('backup_runner',
               default='trove.guestagent.backup.backup_types.InnoBackupEx'),
    cfg.DictOpt('backup_runner_options', default={},
                help='Additional options to be passed to the backup runner.'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('backup_namespace',
               default='trove.guestagent.strategies.backup.mysql_impl',
               help='Namespace to load backup strategies from.'),
    cfg.StrOpt('restore_namespace',
               default='trove.guestagent.strategies.restore.mysql_impl',
               help='Namespace to load restore strategies from.'),
    cfg.DictOpt('backup_incremental_strategy',
                default={'InnoBackupEx': 'InnoBackupExIncremental'},
                help='Incremental Backup Runner based on the default'
                ' strategy. For strategies that do not implement an'
                ' incremental, the runner will use the default full backup.'),
    cfg.BoolOpt('verify_swift_checksum_on_restore', default=True,
                help='Enable verification of swift checksum before starting '
                'restore; makes sure the checksum of original backup matches '
                'checksum of the swift backup file.'),
    cfg.StrOpt('storage_strategy', default='SwiftStorage',
               help="Default strategy to store backups."),
    cfg.StrOpt('storage_namespace',
               default='trove.guestagent.strategies.storage.swift',
               help='Namespace to load the default storage strategy from.'),
    cfg.StrOpt('backup_swift_container', default='database_backups'),
    cfg.BoolOpt('backup_use_gzip_compression', default=True,
                help='Compress backups using gzip.'),
    cfg.BoolOpt('backup_use_openssl_encryption', default=True,
                help='Encrypt backups using OpenSSL.'),
    cfg.StrOpt('backup_aes_cbc_key', default='default_aes_cbc_key',
               help='Default OpenSSL aes_cbc key.'),
    cfg.BoolOpt('backup_use_snet', default=False,
                help='Send backup files over snet.'),
    cfg.IntOpt('backup_chunk_size', default=2 ** 16,
               help='Chunk size to stream to swift container.'
               ' This should be in multiples of 128 bytes, since this is the'
               ' size of an md5 digest block allowing the process to update'
               ' the file checksum during streaming.'
               ' See: http://stackoverflow.com/questions/1131220/'),
    cfg.IntOpt('backup_segment_max_size', default=2 * (1024 ** 3),
               help="Maximum size of each segment of the backup file."),
    cfg.StrOpt('remote_dns_client',
               default='trove.common.remote.dns_client'),
    cfg.StrOpt('remote_guest_client',
               default='trove.common.remote.guest_client'),
    cfg.StrOpt('remote_nova_client',
               default='trove.common.remote.nova_client'),
    cfg.StrOpt('remote_cinder_client',
               default='trove.common.remote.cinder_client'),
    cfg.StrOpt('remote_heat_client',
               default='trove.common.remote.heat_client'),
    cfg.StrOpt('remote_swift_client',
               default='trove.common.remote.swift_client'),
    cfg.StrOpt('exists_notification_transformer',
               help='Transformer for exists notifications.'),
    cfg.IntOpt('exists_notification_ticks', default=360,
               help='Number of report_intervals to wait between pushing '
                    'events (see report_interval).'),
    cfg.DictOpt('notification_service_id',
                default={'mysql': '2f3ff068-2bfb-4f70-9a9d-a6bb65bc084b',
                         'redis': 'b216ffc5-1947-456c-a4cf-70f94c05f7d0',
                         'cassandra': '459a230d-4e97-4344-9067-2a54a310b0ed',
                         'couchbase': 'fa62fe68-74d9-4779-a24e-36f19602c415',
                         'mongodb': 'c8c907af-7375-456f-b929-b637ff9209ee'},
                help='Unique ID to tag notification events.'),
    cfg.StrOpt('nova_proxy_admin_user', default='',
               help="Admin username used to connect to nova.", secret=True),
    cfg.StrOpt('nova_proxy_admin_pass', default='',
               help="Admin password used to connect to nova,", secret=True),
    cfg.StrOpt('nova_proxy_admin_tenant_name', default='',
               help="Admin tenant used to connect to nova.", secret=True),
    cfg.StrOpt('network_label_regex', default='^private$'),
    cfg.StrOpt('ip_regex', default=None),
    cfg.StrOpt('cloudinit_location', default='/etc/trove/cloudinit',
               help="Path to folder with cloudinit scripts."),
    cfg.StrOpt('guest_config',
               default='$pybasedir/etc/trove/trove-guestagent.conf.sample',
               help="Path to guestagent config file."),
    cfg.DictOpt('datastore_registry_ext', default=dict(),
                help='Extension for default datastore managers.'
                     ' Allows to use custom managers for each of'
                     ' datastore supported in trove.'),
    cfg.StrOpt('template_path',
               default='/etc/trove/templates/',
               help='Path which leads to datastore templates.'),
    cfg.BoolOpt('sql_query_logging', default=False,
                help='Allow insecure logging while '
                     'executing queries through SQLAlchemy.'),
    cfg.ListOpt('expected_filetype_suffixes',
                default=['json'],
                help='Filetype endings not to be reattached to an ID '
                     'by the utils method correct_id_with_req.'),
    cfg.ListOpt('default_neutron_networks',
                default=[],
                help='List of network IDs which should be attached'
                     ' to instance when networks are not specified'
                     ' in API call.'),
    cfg.IntOpt('max_header_line', default=16384,
               help='Maximum line size of message headers to be accepted. '
                    'max_header_line may need to be increased when using '
                    'large tokens (typically those generated by the '
                    'Keystone v3 API with big service catalogs).'),
    cfg.StrOpt('conductor_manager', default='trove.conductor.manager.Manager',
               help='Qualified class name to use for conductor manager.')
]

# Datastore specific option groups

# Mysql
mysql_group = cfg.OptGroup(
    'mysql', title='MySQL options',
    help="Oslo option group designed for MySQL datastore")
mysql_opts = [
    cfg.ListOpt('tcp_ports', default=["3306"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UDP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=400,
               help='Timeout to wait for a guest to become active.'),
]

# Percona
percona_group = cfg.OptGroup(
    'percona', title='Percona options',
    help="Oslo option group designed for Percona datastore")
percona_opts = [
    cfg.ListOpt('tcp_ports', default=["3306"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UDP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default='InnoBackupEx',
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql',
               help="Filesystem path for mounting "
                    "volumes if volume support is enabled."),
    cfg.BoolOpt('root_on_create', default=False,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Timeout to wait for a guest to become active.'),
]

# Redis
redis_group = cfg.OptGroup(
    'redis', title='Redis options',
    help="Oslo option group designed for Redis datastore")
redis_opts = [
    cfg.ListOpt('tcp_ports', default=["6379"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UDP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default=None,
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/redis',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Timeout to wait for a guest to become active.'),
]

# Cassandra
cassandra_group = cfg.OptGroup(
    'cassandra', title='Cassandra options',
    help="Oslo option group designed for Cassandra datastore")
cassandra_opts = [
    cfg.ListOpt('tcp_ports', default=["7000", "7001", "9042", "9160"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UDP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default=None,
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/cassandra',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.IntOpt('usage_timeout', default=600,
               help='Timeout to wait for a guest to become active.'),
]

# Couchbase
couchbase_group = cfg.OptGroup(
    'couchbase', title='Couchbase options',
    help="Oslo option group designed for Couchbase datastore")
couchbase_opts = [
    cfg.ListOpt('tcp_ports',
                default=["8091", "8092", "4369", "11209-11211",
                         "21100-21199"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UDP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default=None,
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/couchbase',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Timeout to wait for a guest to become active.'),
    cfg.BoolOpt('root_on_create', default=True,
                help='Enable the automatic creation of the root user for the '
                'service during instance-create. The generated password for '
                'the root user is immediately returned in the response of '
                "instance-create as the 'password' field."),
]

# MongoDB
mongodb_group = cfg.OptGroup(
    'mongodb', title='MongoDB options',
    help="Oslo option group designed for MongoDB datastore")
mongodb_opts = [
    cfg.ListOpt('tcp_ports', default=["2500", "27017"],
                help='List of TCP ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.ListOpt('udp_ports', default=[],
                help='List of UPD ports and/or port ranges to open'
                     ' in the security group (only applicable '
                     'if trove_security_groups_support is True).'),
    cfg.StrOpt('backup_strategy', default=None,
               help='Default strategy to perform backups.'),
    cfg.StrOpt('mount_point', default='/var/lib/mongodb',
               help="Filesystem path for mounting "
               "volumes if volume support is enabled."),
    cfg.IntOpt('usage_timeout', default=450,
               help='Timeout to wait for a guest to become active.'),
]

CONF = cfg.CONF

CONF.register_opts(path_opts)
CONF.register_opts(common_opts)

CONF.register_group(mysql_group)
CONF.register_group(percona_group)
CONF.register_group(redis_group)
CONF.register_group(cassandra_group)
CONF.register_group(couchbase_group)
CONF.register_group(mongodb_group)

CONF.register_opts(mysql_opts, mysql_group)
CONF.register_opts(percona_opts, percona_group)
CONF.register_opts(redis_opts, redis_group)
CONF.register_opts(cassandra_opts, cassandra_group)
CONF.register_opts(couchbase_opts, couchbase_group)
CONF.register_opts(mongodb_opts, mongodb_group)


def custom_parser(parsername, parser):
    CONF.register_cli_opt(cfg.SubCommandOpt(parsername, handler=parser))


def parse_args(argv, default_config_files=None):
    cfg.CONF(args=argv[1:],
             project='trove',
             default_config_files=default_config_files)
