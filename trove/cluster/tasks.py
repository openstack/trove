# Copyright 2014 eBay Software Foundation
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


class ClusterTask(object):
    """
    Stores the different kind of tasks being performed by a cluster.
    """
    _lookup = {}

    def __init__(self, code, name, description):
        self._code = int(code)
        self._name = name
        self._description = description
        ClusterTask._lookup[self._code] = self

    @property
    def code(self):
        return self._code

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._description

    def __eq__(self, other):
        if not isinstance(other, ClusterTask):
            return False
        return self._code == other._code

    @classmethod
    def from_code(cls, code):
        if code not in cls._lookup:
            return None
        return cls._lookup[code]

    def __str__(self):
        return "(%d %s %s)" % (self._code, self._name,
                               self._description)

    def __repr__(self):
        return "ClusterTask.%s (%s)" % (self._name,
                                        self._description)


class ClusterTasks(object):
    NONE = ClusterTask(0x01, 'NONE', 'No tasks for the cluster.')
    BUILDING_INITIAL = ClusterTask(
        0x02, 'BUILDING', 'Building the initial cluster.')
    DELETING = ClusterTask(0x03, 'DELETING', 'Deleting the cluster.')
    ADDING_SHARD = ClusterTask(
        0x04, 'ADDING_SHARD', 'Adding a shard to the cluster.')
    GROWING_CLUSTER = ClusterTask(
        0x05, 'GROWING_CLUSTER', 'Increasing the size of the cluster.')
    SHRINKING_CLUSTER = ClusterTask(
        0x06, 'SHRINKING_CLUSTER', 'Decreasing the size of the cluster.')
    UPGRADING_CLUSTER = ClusterTask(
        0x07, 'UPGRADING_CLUSTER', 'Upgrading the cluster to new version.')
    RESTARTING_CLUSTER = ClusterTask(
        0x08, 'RESTARTING_CLUSTER', 'Restarting the cluster.')


# Dissuade further additions at run-time.
ClusterTask.__init__ = None
