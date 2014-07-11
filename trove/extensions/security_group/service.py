# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#
from trove.common import cfg
from trove.common import exception
from trove.common import wsgi
from trove.common import utils
from trove.datastore.models import DatastoreVersion
from trove.extensions.security_group import models
from trove.extensions.security_group import views
from trove.instance import models as instance_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class SecurityGroupController(wsgi.Controller):
    """Controller for security groups functionality."""

    def index(self, req, tenant_id):
        """Return all security groups tied to a particular tenant_id."""
        LOG.debug("Index() called with %s" % (tenant_id))

        sec_groups = models.SecurityGroup().find_all(tenant_id=tenant_id,
                                                     deleted=False)

        # Construct the mapping from Security Groups to Security Group Rules
        rules_map = dict([(g.id, g.get_rules()) for g in sec_groups])

        return wsgi.Result(
            views.SecurityGroupsView(sec_groups,
                                     rules_map,
                                     req, tenant_id).list(), 200)

    def show(self, req, tenant_id, id):
        """Return a single security group."""
        LOG.debug("Show() called with %s, %s" % (tenant_id, id))

        sec_group = \
            models.SecurityGroup.get_security_group_by_id_or_instance_id(
                id, tenant_id)

        return wsgi.Result(
            views.SecurityGroupView(sec_group,
                                    sec_group.get_rules(),
                                    req, tenant_id).show(), 200)


class SecurityGroupRuleController(wsgi.Controller):
    """Controller for security group rule functionality."""

    def delete(self, req, tenant_id, id):
        LOG.debug("Delete Security Group Rule called %s, %s" % (tenant_id, id))

        context = req.environ[wsgi.CONTEXT_KEY]
        sec_group_rule = models.SecurityGroupRule.find_by(id=id, deleted=False)
        sec_group = sec_group_rule.get_security_group(tenant_id)

        if sec_group is None:
            LOG.error("Attempting to delete Group Rule that does not exist or "
                      "does not belong to tenant %s" % tenant_id)
            raise exception.Forbidden("Unauthorized")

        sec_group_rule.delete(context)
        sec_group.save()
        return wsgi.Result(None, 204)

    def create(self, req, body, tenant_id):
        LOG.debug("Creating a Security Group Rule for tenant '%s'" % tenant_id)

        context = req.environ[wsgi.CONTEXT_KEY]
        self._validate_create_body(body)

        sec_group_id = body['security_group_rule']['group_id']
        sec_group = models.SecurityGroup.find_by(id=sec_group_id,
                                                 tenant_id=tenant_id,
                                                 deleted=False)
        instance_id = (models.SecurityGroupInstanceAssociation.
                       get_instance_id_by_security_group_id(sec_group_id))
        db_info = instance_models.get_db_info(context, id=instance_id)
        manager = (DatastoreVersion.load_by_uuid(
            db_info.datastore_version_id).manager)
        tcp_ports = CONF.get(manager).tcp_ports
        udp_ports = CONF.get(manager).udp_ports

        def _create_rules(sec_group, ports, protocol):
            rules = []
            try:
                for port_or_range in set(ports):
                    from_, to_ = utils.gen_ports(port_or_range)
                    rule = models.SecurityGroupRule.create_sec_group_rule(
                        sec_group, protocol, int(from_), int(to_),
                        body['security_group_rule']['cidr'], context)
                    rules.append(rule)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(msg=str(e))
            return rules

        tcp_rules = _create_rules(sec_group, tcp_ports, 'tcp')
        udp_rules = _create_rules(sec_group, udp_ports, 'udp')

        sec_group.save()

        all_rules = tcp_rules + udp_rules
        view = views.SecurityGroupRulesView(
            all_rules, req, tenant_id).create()
        return wsgi.Result(view, 201)

    def _validate_create_body(self, body):
        try:
            body['security_group_rule']
            body['security_group_rule']['group_id']
            body['security_group_rule']['cidr']
        except KeyError as e:
            LOG.error(_("Create Security Group Rules Required field(s) "
                        "- %s") % e)
            raise exception.SecurityGroupRuleCreationError(
                "Required element/key - %s was not specified" % e)

    schemas = {
        "type": "object",
        "name": "security_group_rule:create",
        "required": True,
        "properties": {
            "security_group_rule": {
                "type": "object",
                "required": True,
                "properties": {
                    "cidr": {
                        "type": "string",
                        "required": True,
                        "minLength": 9,
                        "maxLength": 18
                    },
                    "group_id": {
                        "type": "string",
                        "required": True,
                        "maxLength": 255
                    },
                }
            }
        }
    }
