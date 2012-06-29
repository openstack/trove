# Copyright 2012 OpenStack LLC.
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
Common instance status code used across Reddwarf API.
"""


class InstanceTask(object):
    """
    Stores the different kind of tasks being performed by an instance.
    """
    #TODO(tim.simpson): Figure out someway to migrate this to the TaskManager
    #                   once that revs up.
    _lookup = {}

    def __init__(self, code, action, db_text, is_error=False):
        self._code = int(code)
        self._action = action
        self._db_text = db_text
        self._is_error = is_error
        InstanceTask._lookup[self._code] = self

    @property
    def action(self):
        return self._action

    @property
    def code(self):
        return self._code

    @property
    def db_text(self):
        return self._db_text

    @property
    def is_error(self):
        return self._is_error

    def __eq__(self, other):
        if not isinstance(other, InstanceTask):
            return False
        return self._db_text == other._db_text

    @classmethod
    def from_code(cls, code):
        if code not in cls._lookup:
            return None
        return cls._lookup[code]


class InstanceTasks(object):
    NONE = InstanceTask(0x01, 'NONE', 'No tasks for the instance.')
    DELETING = InstanceTask(0x02, 'DELETING', 'Deleting the instance.')
    REBOOTING = InstanceTask(0x03, 'REBOOTING', 'Rebooting the instance.')
    RESIZING = InstanceTask(0x04, 'RESIZING', 'Resizing the instance.')
    BUILDING = InstanceTask(0x05, 'BUILDING', 'The instance is building.')

    BUILDING_ERROR_DNS = InstanceTask(0x50, 'BUILDING',
        'Build error: DNS.', is_error=True)
    BUILDING_ERROR_SERVER = InstanceTask(0x51, 'BUILDING',
        'Build error: Server.', is_error=True)
    BUILDING_ERROR_VOLUME = InstanceTask(0x52, 'BUILDING',
        'Build error: Volume.', is_error=True)


# Dissuade further additions at run-time.
InstanceTask.__init__ = None
