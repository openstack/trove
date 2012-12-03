# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Model classes that form the core of instances functionality."""

from reddwarf.openstack.common import log as logging
from reddwarf.common import remote


LOG = logging.getLogger(__name__)


class ModelBase(object):
    """
    An object which can be stored in the database.
    """

    _data_fields = []
    _auto_generated_attrs = []

    def _validate(self, errors):
        """Subclasses override this to offer additional validation.

        For each validation error a key with the field name and an error
        message is added to the dict.

        """
        pass

    def data(self, **options):
        """Called to serialize object to a dictionary."""
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, self[field]) for field in data_fields])

    def is_valid(self):
        """Called when persisting data to ensure the format is correct."""
        self.errors = {}
        self._validate(self.errors)
#        self._validate_columns_type()
#        self._before_validate()
#        self._validate()
        return self.errors == {}

    def __setitem__(self, key, value):
        """Overloaded to cause this object to look like a data entity."""
        setattr(self, key, value)

    def __getitem__(self, key):
        """Overloaded to cause this object to look like a data entity."""
        return getattr(self, key)

    def __eq__(self, other):
        """Overloaded to cause this object to look like a data entity."""
        if not hasattr(other, 'id'):
            return False
        return type(other) == type(self) and other.id == self.id

    def __ne__(self, other):
        """Overloaded to cause this object to look like a data entity."""
        return not self == other

    def __hash__(self):
        """Overloaded to cause this object to look like a data entity."""
        return self.id.__hash__()


class NovaRemoteModelBase(ModelBase):

    # This should be set by the remote model during init time
    # The data() method will be using this
    _data_object = None

    @classmethod
    def get_client(cls, context):
        return remote.create_nova_client(context)

    def _data_item(self, data_object):
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, getattr(data_object, field))
                     for field in data_fields])

    # data magic that will allow for a list of _data_object or a single item
    # if the object is a list, it will turn it into a list of hash's again
    def data(self, **options):
        if self._data_object is None:
            raise LookupError("data object is None")
        if isinstance(self._data_object, list):
            return [self._data_item(item) for item in self._data_object]
        else:
            return self._data_item(self._data_object)
