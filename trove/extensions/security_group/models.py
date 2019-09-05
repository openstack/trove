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

"""
Model classes for Security Groups and Security Group Rules on instances.
"""
from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.models import NetworkRemoteModelBase
from trove.db.models import DatabaseModelBase


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def persisted_models():
    return {
        'security_groups': SecurityGroup,
        'security_group_rules': SecurityGroupRule,
        'security_group_instance_associations':
        SecurityGroupInstanceAssociation,
    }


class SecurityGroup(DatabaseModelBase):
    _data_fields = ['name', 'description', 'user', 'tenant_id',
                    'created', 'updated', 'deleted', 'deleted_at']
    _table_name = 'security_groups'

    @property
    def instance_id(self):
        return SecurityGroupInstanceAssociation.\
            get_instance_id_by_security_group_id(self.id)

    @classmethod
    def get_security_group_by_id_or_instance_id(cls, id, tenant_id):
        try:
            return SecurityGroup.find_by(id=id,
                                         tenant_id=tenant_id,
                                         deleted=False)
        except exception.ModelNotFoundError:
            return SecurityGroupInstanceAssociation.\
                get_security_group_by_instance_id(id)

    def get_rules(self):
        return SecurityGroupRule.find_all(group_id=self.id,
                                          deleted=False)

    def delete(self, context, region_name):
        try:
            sec_group_rules = self.get_rules()
            if sec_group_rules:
                for rule in sec_group_rules:
                    rule.delete(context, region_name)

            RemoteSecurityGroup.delete(self.id, context, region_name)
            super(SecurityGroup, self).delete()

        except exception.TroveError:
            LOG.exception('Failed to delete security group.')
            raise exception.TroveError("Failed to delete Security Group")

    @classmethod
    def delete_for_instance(cls, instance_id, context, region_name):
        try:
            association = SecurityGroupInstanceAssociation.find_by(
                instance_id=instance_id,
                deleted=False)
            if association:
                sec_group = association.get_security_group()
                if sec_group:
                    sec_group.delete(context, region_name)
                association.delete()
        except (exception.ModelNotFoundError, exception.TroveError):
            pass


class SecurityGroupRule(DatabaseModelBase):
    _data_fields = ['group_id', 'parent_group_id', 'protocol',
                    'from_port', 'to_port', 'cidr', 'created',
                    'updated', 'deleted', 'deleted_at']
    _table_name = 'security_group_rules'

    def get_security_group(self, tenant_id):
        return SecurityGroup.find_by(id=self.group_id,
                                     tenant_id=tenant_id,
                                     deleted=False)

    def delete(self, context, region_name):
        try:
            # Delete Remote Security Group Rule
            RemoteSecurityGroup.delete_rule(self.id, context, region_name)
            super(SecurityGroupRule, self).delete()
        except exception.TroveError:
            LOG.exception('Failed to delete remote security group rule.')
            raise exception.SecurityGroupRuleDeletionError(
                "Failed to delete Remote Security Group Rule")


class SecurityGroupInstanceAssociation(DatabaseModelBase):
    _data_fields = ['security_group_id', 'instance_id', 'created',
                    'updated', 'deleted', 'deleted_at']
    _table_name = 'security_group_instance_associations'

    def get_security_group(self):
        return SecurityGroup.find_by(id=self.security_group_id,
                                     deleted=False)

    @classmethod
    def get_security_group_by_instance_id(cls, id):
        association = SecurityGroupInstanceAssociation.find_by(
            instance_id=id,
            deleted=False)
        return association.get_security_group()

    @classmethod
    def get_instance_id_by_security_group_id(cls, secgroup_id):
        association = SecurityGroupInstanceAssociation.find_by(
            security_group_id=secgroup_id,
            deleted=False)
        return association.instance_id


class RemoteSecurityGroup(NetworkRemoteModelBase):

    _data_fields = ['id', 'name', 'description', 'rules']

    def __init__(self, security_group=None, id=None, context=None,
                 region_name=None):
        if id is None and security_group is None:
            msg = _("Security Group does not have id defined!")
            raise exception.InvalidModelError(msg)
        elif security_group is None:
            driver = self.get_driver(context,
                                     region_name or CONF.os_region_name)
            self._data_object = driver.get_sec_group_by_id(group_id=id)
        else:
            self._data_object = security_group

    @classmethod
    def delete(cls, sec_group_id, context, region_name):
        """Deletes a Security Group."""
        driver = cls.get_driver(context, region_name)
        driver.delete_security_group(sec_group_id)

    @classmethod
    def delete_rule(cls, sec_group_rule_id, context, region_name):
        """Deletes a rule from an existing security group."""
        driver = cls.get_driver(context, region_name)
        driver.delete_security_group_rule(sec_group_rule_id)
