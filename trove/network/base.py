# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
import abc

import six


@six.add_metaclass(abc.ABCMeta)
class NetworkDriver(object):
    """Base Network Driver class to abstract the network driver used."""

    @abc.abstractmethod
    def get_sec_group_by_id(self, group_id):
        """
        Returns security group with given group_id
        """

    @abc.abstractmethod
    def create_security_group(self, name, description):
        """
        Creates the security group with given name and description
        """

    @abc.abstractmethod
    def delete_security_group(self, sec_group_id):
        """Deletes the security group by given ID."""

    @abc.abstractmethod
    def add_security_group_rule(self, sec_group_id, protocol,
                                from_port, to_port, cidr):
        """
        Adds the rule identified by the security group ID,
        transport protocol, port range: from -> to, CIDR.
        """

    @abc.abstractmethod
    def delete_security_group_rule(self, sec_group_rule_id):
        """Deletes the rule by given ID."""
