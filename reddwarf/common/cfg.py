# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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
"""Routines for configuring Reddwarf."""

from oslo.config import cfg

common_opts = [
    cfg.StrOpt('sql_connection',
               default='sqlite:///reddwarf_test.sqlite',
               help='SQL Connection'),
    cfg.IntOpt('sql_idle_timeout', default=3600),
    cfg.BoolOpt('sql_query_log', default=False),
    cfg.IntOpt('bind_port', default=8779),
    cfg.StrOpt('api_extensions_path', default='',
               help='Path to extensions'),
    cfg.StrOpt('api_paste_config',
               default="api-paste.ini",
               help='File name for the paste.deploy config for reddwarf-api'),
    cfg.BoolOpt('add_addresses',
                default=False,
                help='Whether to add IP addresses to the list operations'),
    cfg.BoolOpt('reddwarf_volume_support',
                default=True,
                help='File name for the paste.deploy config for reddwarf-api'),
    cfg.ListOpt('admin_roles', default=[]),
    cfg.StrOpt('remote_implementation',
               default="real",
               help='Remote implementation for using fake integration code'),
    cfg.StrOpt('nova_compute_url', default='http://localhost:8774/v2'),
    cfg.StrOpt('nova_volume_url', default='http://localhost:8776/v2'),
    cfg.StrOpt('reddwarf_auth_url', default='http://0.0.0.0:5000/v2.0'),
    cfg.StrOpt('backup_swift_container', default='DBaaS-backup'),
    cfg.StrOpt('host', default='0.0.0.0'),
    cfg.IntOpt('report_interval', default=10),
    cfg.IntOpt('periodic_interval', default=60),
    cfg.BoolOpt('reddwarf_dns_support', default=False),
    cfg.StrOpt('db_api_implementation', default='reddwarf.db.sqlalchemy.api'),
    cfg.StrOpt('mysql_pkg', default='mysql-server-5.5'),
    cfg.StrOpt('dns_driver', default='reddwarf.dns.driver.DnsDriver'),
    cfg.StrOpt('dns_instance_entry_factory',
               default='reddwarf.dns.driver.DnsInstanceEntryFactory'),
    cfg.StrOpt('dns_hostname', default=""),
    cfg.IntOpt('dns_account_id', default=0),
    cfg.StrOpt('dns_auth_url', default=""),
    cfg.StrOpt('dns_domain_name', default=""),
    cfg.StrOpt('dns_username', default=""),
    cfg.StrOpt('dns_passkey', default=""),
    cfg.StrOpt('dns_management_base_url', default=""),
    cfg.IntOpt('dns_ttl', default=300),
    cfg.IntOpt('dns_domain_id', default=1),
    cfg.IntOpt('users_page_size', default=20),
    cfg.IntOpt('databases_page_size', default=20),
    cfg.IntOpt('instances_page_size', default=20),
    cfg.ListOpt('ignore_users', default=[]),
    cfg.ListOpt('ignore_dbs', default=[]),
    cfg.IntOpt('agent_call_low_timeout', default=5),
    cfg.IntOpt('agent_call_high_timeout', default=60),
    cfg.StrOpt('guest_id', default=None),
    cfg.IntOpt('state_change_wait_time', default=3 * 60),
    cfg.IntOpt('agent_heartbeat_time', default=10),
    cfg.IntOpt('num_tries', default=3),
    cfg.StrOpt('volume_fstype', default='ext3'),
    cfg.StrOpt('format_options', default='-m 5'),
    cfg.IntOpt('volume_format_timeout', default=120),
    cfg.StrOpt('mount_options', default='defaults,noatime'),
    cfg.IntOpt('max_instances_per_user', default=5,
               help='default maximum number of instances per tenant'),
    cfg.IntOpt('max_accepted_volume_size', default=5,
               help='default maximum volume size for an instance'),
    cfg.IntOpt('max_volumes_per_user', default=20,
               help='default maximum for total volume used by a tenant'),
    cfg.StrOpt('quota_driver',
               default='reddwarf.quota.quota.DbQuotaDriver',
               help='default driver to use for quota checks'),
    cfg.StrOpt('taskmanager_queue', default='taskmanager'),
    cfg.BoolOpt('use_nova_server_volume', default=False),
    cfg.StrOpt('fake_mode_events', default='simulated'),
    cfg.StrOpt('device_path', default='/dev/vdb'),
    cfg.StrOpt('mount_point', default='/var/lib/mysql'),
    cfg.StrOpt('service_type', default='mysql'),
    cfg.StrOpt('block_device_mapping', default='vdb'),
    cfg.IntOpt('server_delete_time_out', default=2),
    cfg.IntOpt('volume_time_out', default=2),
    cfg.IntOpt('reboot_time_out', default=60 * 2),
    cfg.StrOpt('service_options', default=['mysql']),
    cfg.IntOpt('dns_time_out', default=60 * 2),
    cfg.IntOpt('resize_time_out', default=60 * 10),
    cfg.IntOpt('revert_time_out', default=60 * 10),
    cfg.ListOpt('root_grant', default=['ALL']),
    cfg.BoolOpt('root_grant_option', default=True),
    cfg.IntOpt('http_get_rate', default=200),
    cfg.IntOpt('http_post_rate', default=200),
    cfg.IntOpt('http_delete_rate', default=200),
    cfg.IntOpt('http_put_rate', default=200),
    cfg.BoolOpt('hostname_require_ipv4', default=True,
                help="Require user hostnames to be IPv4 addresses."),
    cfg.BoolOpt('reddwarf_security_groups_support', default=True),
    cfg.StrOpt('reddwarf_security_group_rule_protocol', default='tcp'),
    cfg.IntOpt('reddwarf_security_group_rule_port', default=3306),
]


CONF = cfg.CONF
CONF.register_opts(common_opts)


def custom_parser(parsername, parser):
    CONF.register_cli_opt(cfg.SubCommandOpt(parsername, handler=parser))


def parse_args(argv, default_config_files=None):
    cfg.CONF(args=argv[1:],
             project='reddwarf',
             default_config_files=default_config_files)
