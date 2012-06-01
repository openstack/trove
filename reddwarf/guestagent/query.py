# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

"""

Intermediary class for building SQL queries for use by the guest agent.

"""


class Query(object):

    def __init__(self, columns=[], tables=[], where=[], order=[], limit=0):
        self.columns = columns
        self.tables = tables
        self.where = where
        self.order = order
        self.limit = limit

    @property
    def _columns(self):
        return ', '.join(self.columns) if self.columns else "*"

    @property
    def _tables(self):
        return ', '.join(self.tables)

    @property
    def _where(self):
        if not self.where:
            return ""
        return "WHERE %s" % (" AND ".join(self.where))

    @property
    def _order(self):
        if not self.order:
            return ''
        return "ORDER BY %s" % (', '.join(self.order))

    @property
    def _limit(self):
        if not self.limit:
            return ''
        return "LIMIT %s" % str(self.limit)

    def __str__(self):
        query = [
            "SELECT %s" % self._columns,
            "FROM %s" % self._tables,
            self._where,
            self._order,
            self._limit
            ]
        return '\n'.join(query)

    def __repr__(self):
        return str(self)
