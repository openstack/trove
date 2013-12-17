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

import abc
from trove.guestagent.strategy import Strategy


class Storage(Strategy):
    """Base class for Storage Strategy implementation """
    __strategy_type__ = 'storage'
    __strategy_ns__ = 'trove.guestagent.strategies.storage'

    def __init__(self, context):
        self.context = context
        super(Storage, self).__init__()

    @abc.abstractmethod
    def save(self, filename, stream):
        """Persist information from the stream """

    @abc.abstractmethod
    def load(self, context, location, is_zipped, backup_checksum):
        """Load a stream from a persisted storage location  """
