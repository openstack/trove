# Copyright 2016 Tesora Inc.
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


from oslo_config import cfg
from oslo_policy import policy

from trove.common import exception as trove_exceptions

CONF = cfg.CONF
_ENFORCER = None


base_rules = [
    policy.RuleDefault(
        'admin',
        'role:admin or is_admin:True',
        description='Must be an administrator.'),
    policy.RuleDefault(
        'admin_or_owner',
        'rule:admin or tenant:%(tenant)s',
        description='Must be an administrator or owner of the object.'),
    policy.RuleDefault(
        'default',
        'rule:admin_or_owner',
        description='Must be an administrator or owner of the object.')
]

instance_rules = [
    policy.RuleDefault(
        'instance:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:force_delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:update', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:edit', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:restart', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:resize_volume', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:resize_flavor', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:reset_status', 'rule:admin'),
    policy.RuleDefault(
        'instance:promote_to_replica_source', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:eject_replica_source', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:configuration', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:guest_log_list', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:backups', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:module_list', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:module_apply', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:module_remove', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'instance:extension:root:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:root:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:root:index', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'instance:extension:user:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user:update', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user:update_all', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'instance:extension:user_access:update', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user_access:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:user_access:index', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'instance:extension:database:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:database:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:database:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'instance:extension:database:show', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'cluster:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:force_delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:show_instance', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:action', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:reset-status', 'rule:admin'),

    policy.RuleDefault(
        'cluster:extension:root:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:extension:root:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'cluster:extension:root:index', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'backup:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'backup:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'backup:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'backup:show', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'configuration:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:instances', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:update', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration:edit', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'configuration-parameter:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration-parameter:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration-parameter:index_by_version', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'configuration-parameter:show_by_version', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'datastore:index', ''),
    policy.RuleDefault(
        'datastore:show', ''),
    policy.RuleDefault(
        'datastore:version_show', ''),
    policy.RuleDefault(
        'datastore:version_show_by_uuid', ''),
    policy.RuleDefault(
        'datastore:version_index', ''),
    policy.RuleDefault(
        'datastore:list_associated_flavors', ''),
    policy.RuleDefault(
        'datastore:list_associated_volume_types', ''),

    policy.RuleDefault(
        'flavor:index', ''),
    policy.RuleDefault(
        'flavor:show', ''),

    policy.RuleDefault(
        'limits:index', 'rule:admin_or_owner'),

    policy.RuleDefault(
        'module:create', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:delete', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:index', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:show', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:instances', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:update', 'rule:admin_or_owner'),
    policy.RuleDefault(
        'module:reapply', 'rule:admin_or_owner'),
]


def get_enforcer():
    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(CONF)
        _ENFORCER.register_defaults(base_rules)
        _ENFORCER.register_defaults(instance_rules)
        _ENFORCER.load_rules()
    return _ENFORCER


def authorize_on_tenant(context, rule):
    return __authorize(context, rule, target=None)


def authorize_on_target(context, rule, target):
    if target:
        return __authorize(context, rule, target=target)
    raise trove_exceptions.TroveError(
        "BUG: Target must not evaluate to False.")


def __authorize(context, rule, target=None):
    """Checks authorization of a rule against the target in this context.

    * This function is not to be called directly.
      Calling the function with a target that evaluates to None may
      result in policy bypass.
      Use 'authorize_on_*' calls instead.

       :param context   Trove context.
       :type context    Context.

       :param rule:     The rule to evaluate.
                        e.g. ``instance:create_instance``,
                             ``instance:resize_volume``

       :param target    As much information about the object being operated on
                        as possible.
                        For object creation (target=None) this should be a
                        dictionary representing the location of the object
                        e.g. ``{'project_id': context.project_id}``
       :type target     dict

       :raises:         :class:`PolicyNotAuthorized` if verification fails.

    """
    target = target or {'tenant': context.tenant}
    return get_enforcer().authorize(
        rule, target, context.to_dict(), do_raise=True,
        exc=trove_exceptions.PolicyNotAuthorized, action=rule)
