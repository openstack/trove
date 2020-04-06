# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import abc


class Storage(object):
    """Base class for Storage driver implementation."""

    @abc.abstractmethod
    def save(self, stream, metadata=None, **kwargs):
        """Persist information from the stream.

        Should return the new backup checkshum and location.
        """

    @abc.abstractmethod
    def load(self, location, backup_checksum, **kwargs):
        """Load a stream from the data location.

        Should return an object that provides "read" method.
        """

    def load_metadata(self, parent_location, parent_checksum):
        """Load metadata for a parent backup.

        It's up to the storage driver to decide how to implement this function.
        """
        return {}

    def is_incremental_backup(self, location):
        """Check if the location is an incremental backup."""
        return False

    @abc.abstractmethod
    def get_backup_lsn(self, location):
        """Get the backup LSN."""
