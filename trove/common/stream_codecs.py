# Copyright 2015 Tesora Inc.
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

import abc
import ast
import csv
import json
import six
import StringIO
import yaml

from ConfigParser import SafeConfigParser

from trove.common import utils as trove_utils


class StringConverter(object):
    """A passthrough string-to-object converter.
    """

    def __init__(self, object_mappings):
        """
        :param object_mappings:  string-to-object mappings
        :type object_mappings:   dict
        """
        self._object_mappings = object_mappings

    def to_strings(self, items):
        """Recursively convert collection items to strings.

        :returns:        Copy of the input collection with all items converted.
        """
        if trove_utils.is_collection(items):
            return map(self.to_strings, items)

        return self._to_string(items)

    def to_objects(self, items):
        """Recursively convert collection string to objects.

        :returns:        Copy of the input collection with all items converted.
        """
        if trove_utils.is_collection(items):
            return map(self.to_objects, items)

        return self._to_object(items)

    def _to_string(self, value):
        for k, v in self._object_mappings.items():
            if v is value:
                return k

        return str(value)

    def _to_object(self, value):
        if value in self._object_mappings:
            return self._object_mappings[value]

        try:
            return ast.literal_eval(value)
        except Exception:
            return value


@six.add_metaclass(abc.ABCMeta)
class StreamCodec(object):

    @abc.abstractmethod
    def serialize(self, data):
        """Serialize a Python object into a stream.
        """

    @abc.abstractmethod
    def deserialize(self, stream):
        """Deserialize stream data into a Python structure.
        """


class IdentityCodec(StreamCodec):
    """
    A basic passthrough codec.
    Does not modify the data in any way.
    """

    def serialize(self, data):
        return data

    def deserialize(self, stream):
        return stream


class YamlCodec(StreamCodec):
    """
    Read/write data from/into a YAML config file.

    a: 1
    b: {c: 3, d: 4}
    ...

    The above file content (flow-style) would be represented as:
    {'a': 1,
     'b': {'c': 3, 'd': 4,}
     ...
    }
    """

    def __init__(self, default_flow_style=False):
        """
        :param default_flow_style:  Use flow-style (inline) formatting of
                                    nested collections.
        :type default_flow_style:   boolean
        """
        self._default_flow_style = default_flow_style

    def serialize(self, dict_data):
        return yaml.dump(dict_data, Dumper=self.dumper,
                         default_flow_style=self._default_flow_style)

    def deserialize(self, stream):
        return yaml.load(stream, Loader=self.loader)

    @property
    def loader(self):
        return yaml.loader.Loader

    @property
    def dumper(self):
        return yaml.dumper.Dumper


class SafeYamlCodec(YamlCodec):
    """
    Same as YamlCodec except that it uses safe Loader and Dumper which
    encode Unicode strings and produce only basic YAML tags.
    """

    def __init__(self, default_flow_style=False):
        super(SafeYamlCodec, self).__init__(
            default_flow_style=default_flow_style)

    @property
    def loader(self):
        return yaml.loader.SafeLoader

    @property
    def dumper(self):
        return yaml.dumper.SafeDumper


class IniCodec(StreamCodec):
    """
    Read/write data from/into an ini-style config file.

    [section_1]
    key = value
    key = value
    ...

    [section_2]
    key = value
    key = value
    ...

    The above file content would be represented as:
    {'section_1': {'key': 'value', 'key': 'value', ...},
     'section_2': {'key': 'value', 'key': 'value', ...}
     ...
    }
    """

    def __init__(self, default_value=None, comment_markers=('#', ';')):
        """
        :param default_value:  Default value for keys with no value.
                               If set, all keys are written as 'key = value'.
                               The key is written without trailing '=' if None.
        :type default_value:   string
        """
        self._value_converter = StringConverter({default_value: None})
        self._default_value = default_value
        self._comment_markers = comment_markers

    def serialize(self, dict_data):
        parser = self._init_config_parser(dict_data)
        output = StringIO.StringIO()
        parser.write(output)

        return output.getvalue()

    def deserialize(self, stream):
        parser = self._init_config_parser()
        parser.readfp(self._pre_parse(stream))

        return {s: {k: self._value_converter.to_strings(v)
                    for k, v in parser.items(s, raw=True)}
                for s in parser.sections()}

    def _pre_parse(self, stream):
        buf = StringIO.StringIO()
        for line in StringIO.StringIO(stream):
            # Ignore commented lines.
            if not line.startswith(self._comment_markers):
                # Strip leading and trailing whitespaces from each line.
                buf.write(line.strip() + '\n')

        # Rewind the output buffer.
        buf.flush()
        buf.seek(0)

        return buf

    def _init_config_parser(self, sections=None):
        parser = SafeConfigParser(allow_no_value=True)
        if sections:
            for section in sections:
                parser.add_section(section)
                for key, value in sections[section].items():
                    parser.set(section, key,
                               self._value_converter.to_strings(value))

        return parser


class PropertiesCodec(StreamCodec):
    """
    Read/write data from/into a property-style config file.

    key1 k1arg1 k1arg2 ... k1argN
    key2 k2arg1 k2arg2 ... k2argN
    key3 k3arg1 k3arg2 ...
    key3 k3arg3 k3arg4 ...
    ...

    The above file content would be represented as:
    {'key1': [k1arg1, k1arg2 ... k1argN],
     'key2': [k2arg1, k2arg2 ... k2argN]
     'key3': [[k3arg1, k3arg2, ...], [k3arg3, k3arg4, ...]]
     ...
    }
    """

    QUOTING_MODE = csv.QUOTE_MINIMAL
    STRICT_MODE = False

    def __init__(self, delimiter=' ', comment_markers=('#'),
                 unpack_singletons=True, string_mappings={}):
        """
        :param delimiter:         A one-character used to separate fields.
        :type delimiter:          string

        :param empty_value:       Value to represent None in the output.
        :type empty_value:        object

        :param comment_markers:   List of comment markers.
        :type comment_markers:    list

        :param unpack_singletons: Whether to unpack singleton collections
                                  (collections with only a single value).
        :type unpack_singletons:  boolean

        :param string_mappings:   User-defined string representations of
                                  Python objects.
        :type string_mappings:    dict
        """
        self._delimiter = delimiter
        self._comment_markers = comment_markers
        self._string_converter = StringConverter(string_mappings)
        self._unpack_singletons = unpack_singletons

    def serialize(self, dict_data):
        output = StringIO.StringIO()
        writer = csv.writer(output, delimiter=self._delimiter,
                            quoting=self.QUOTING_MODE,
                            strict=self.STRICT_MODE)

        for key, value in sorted(dict_data.items()):
            writer.writerows(self._to_rows(key, value))

        return output.getvalue()

    def deserialize(self, stream):
        reader = csv.reader(StringIO.StringIO(stream),
                            delimiter=self._delimiter,
                            quoting=self.QUOTING_MODE,
                            strict=self.STRICT_MODE)

        return self._to_dict(reader)

    def _to_dict(self, reader):
        data_dict = {}
        for row in reader:
            # Ignore comment lines.
            if row and not row[0].startswith(self._comment_markers):
                items = self._string_converter.to_objects(
                    [v if v else None for v in row[1:]])
                current = data_dict.get(row[0])
                if current is not None:
                    current.append(trove_utils.unpack_singleton(items)
                                   if self._unpack_singletons else items)
                else:
                    data_dict.update({row[0]: [items]})

        if self._unpack_singletons:
            # Unpack singleton values.
            for k, v in data_dict.items():
                data_dict.update({k: trove_utils.unpack_singleton(v)})

        return data_dict

    def _to_rows(self, header, items):
        rows = []
        if trove_utils.is_collection(items):
            if any(trove_utils.is_collection(item) for item in items):
                # This is multi-row property.
                for item in items:
                    rows.extend(self._to_rows(header, item))
            else:
                # This is a single-row property with multiple arguments.
                rows.append(self._to_list(
                    header, self._string_converter.to_strings(items)))
        else:
            # This is a single-row property with only one argument.
            rows.append(self._to_list(header, items))

        return rows

    def _to_list(self, *items):
        container = []
        for item in items:
            if trove_utils.is_collection(item):
                # This item is a nested collection - unpack it.
                container.extend(self._to_list(*item))
            else:
                # This item is not a collection - append it to the list.
                container.append(item)

        return container


class JsonCodec(StreamCodec):

    def serialize(self, dict_data):
        return json.dumps(dict_data)

    def deserialize(self, stream):
        return json.load(StringIO.StringIO(stream))
