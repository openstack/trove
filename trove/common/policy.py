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
from trove.common import policies

CONF = cfg.CONF
_ENFORCER = None


def get_enforcer():
    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(CONF)
        _ENFORCER.register_defaults(policies.list_rules())
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
    target = target or {'tenant': context.project_id}
    return get_enforcer().authorize(
        rule, target, context.to_dict(), do_raise=True,
        exc=trove_exceptions.PolicyNotAuthorized, action=rule)
