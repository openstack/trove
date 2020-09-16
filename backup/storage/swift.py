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

import hashlib
import json

from keystoneauth1 import session
from keystoneauth1.identity import v3
from oslo_config import cfg
from oslo_log import log as logging
import swiftclient

from backup.storage import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def _get_user_keystone_session(auth_url, token, tenant_id):
    auth = v3.Token(
        auth_url=auth_url, token=token,
        project_domain_name="Default",
        project_id=tenant_id
    )
    return session.Session(auth=auth, verify=False)


def _get_service_client(auth_url, token, tenant_id):
    sess = _get_user_keystone_session(auth_url, token, tenant_id)
    return swiftclient.Connection(session=sess)


def _set_attr(original):
    """Return a swift friendly header key."""
    key = original.replace('_', '-')
    return 'X-Object-Meta-%s' % key


def _get_attr(original):
    """Get a friendly name from an object header key."""
    key = original.replace('-', '_')
    key = key.replace('x_object_meta_', '')
    return key


class StreamReader(object):
    """Wrap the stream from the backup process and chunk it into segements."""

    def __init__(self, stream, container, filename, max_file_size):
        self.stream = stream
        self.container = container
        self.filename = filename
        self.max_file_size = max_file_size
        self.segment_length = 0
        self.process = None
        self.file_number = 0
        self.end_of_file = False
        self.end_of_segment = False
        self.segment_checksum = hashlib.md5()

    @property
    def base_filename(self):
        """Filename with extensions removed."""
        return self.filename.split('.')[0]

    @property
    def segment(self):
        return '%s_%08d' % (self.base_filename, self.file_number)

    @property
    def first_segment(self):
        return '%s_%08d' % (self.base_filename, 0)

    @property
    def segment_path(self):
        return '%s/%s' % (self.container, self.segment)

    def read(self, chunk_size=2 ** 16):
        if self.end_of_segment:
            self.segment_length = 0
            self.segment_checksum = hashlib.md5()
            self.end_of_segment = False

        # Upload to a new file if we are starting or too large
        if self.segment_length > (self.max_file_size - chunk_size):
            self.file_number += 1
            self.end_of_segment = True
            return ''

        chunk = self.stream.read(chunk_size)
        if not chunk:
            self.end_of_file = True
            return ''

        self.segment_checksum.update(chunk)
        self.segment_length += len(chunk)
        return chunk


class SwiftStorage(base.Storage):
    def __init__(self):
        self.client = _get_service_client(CONF.os_auth_url, CONF.os_token,
                                          CONF.os_tenant_id)

    def save(self, stream, metadata=None, container='database_backups'):
        """Persist data from the stream to swift.

        * Read data from stream, upload to swift
        * Update the new object metadata, stream provides method to get
          metadata.

        :returns the new object checkshum and swift full URL.
        """
        filename = stream.manifest
        LOG.info('Saving %(filename)s to %(container)s in swift.',
                 {'filename': filename, 'container': container})

        # Create the container if it doesn't already exist
        LOG.debug('Ensuring container %s', container)
        self.client.put_container(container)

        # Swift Checksum is the checksum of the concatenated segment checksums
        swift_checksum = hashlib.md5()
        # Wrap the output of the backup process to segment it for swift
        stream_reader = StreamReader(stream, container, filename,
                                     2 * (1024 ** 3))

        url = self.client.url
        # Full location where the backup manifest is stored
        location = "%s/%s/%s" % (url, container, filename)
        LOG.info('Uploading to %s', location)

        # Information about each segment upload job
        segment_results = []

        # Read from the stream and write to the container in swift
        while not stream_reader.end_of_file:
            LOG.debug('Uploading segment %s.', stream_reader.segment)
            path = stream_reader.segment_path
            etag = self.client.put_object(container,
                                          stream_reader.segment,
                                          stream_reader)

            segment_checksum = stream_reader.segment_checksum.hexdigest()

            # Check each segment MD5 hash against swift etag
            if etag != segment_checksum:
                msg = ('Failed to upload data segment to swift. ETAG: %(tag)s '
                       'Segment MD5: %(checksum)s.' %
                       {'tag': etag, 'checksum': segment_checksum})
                raise Exception(msg)

            segment_results.append({
                'path': path,
                'etag': etag,
                'size_bytes': stream_reader.segment_length
            })

            swift_checksum.update(segment_checksum.encode())

        # All segments uploaded.
        num_segments = len(segment_results)
        LOG.debug('File uploaded in %s segments.', num_segments)

        # An SLO will be generated if the backup was more than one segment in
        # length.
        large_object = num_segments > 1

        # Meta data is stored as headers
        if metadata is None:
            metadata = {}
        metadata.update(stream.get_metadata())
        headers = {}
        for key, value in metadata.items():
            headers[_set_attr(key)] = value

        LOG.info('Metadata headers: %s', headers)
        if large_object:
            manifest_data = json.dumps(segment_results)
            LOG.info('Creating the SLO manifest file, manifest content: %s',
                     manifest_data)
            # The etag returned from the manifest PUT is the checksum of the
            # manifest object (which is empty); this is not the checksum we
            # want.
            self.client.put_object(container,
                                   filename,
                                   manifest_data,
                                   query_string='multipart-manifest=put')

            # Validation checksum is the Swift Checksum
            final_swift_checksum = swift_checksum.hexdigest()
        else:
            LOG.info('Moving segment %(segment)s to %(filename)s.',
                     {'segment': stream_reader.first_segment,
                      'filename': filename})
            segment_result = segment_results[0]
            # Just rename it via a special put copy.
            headers['X-Copy-From'] = segment_result['path']
            self.client.put_object(container,
                                   filename, '',
                                   headers=headers)

            # Delete the old segment file that was copied
            LOG.info('Deleting the old segment file %s.',
                     stream_reader.first_segment)
            try:
                self.client.delete_object(container,
                                          stream_reader.first_segment)
            except swiftclient.exceptions.ClientException as e:
                if e.http_status != 404:
                    raise

            final_swift_checksum = segment_result['etag']

        # Validate the object by comparing checksums
        resp = self.client.head_object(container, filename)
        # swift returns etag in double quotes
        # e.g. '"dc3b0827f276d8d78312992cc60c2c3f"'
        etag = resp['etag'].strip('"')

        # Raise an error and mark backup as failed
        if etag != final_swift_checksum:
            msg = ('Failed to upload data to swift. Manifest ETAG: %(tag)s '
                   'Swift MD5: %(checksum)s' %
                   {'tag': etag, 'checksum': final_swift_checksum})
            raise Exception(msg)

        return (final_swift_checksum, location)

    def _explodeLocation(self, location):
        storage_url = "/".join(location.split('/')[:-2])
        container = location.split('/')[-2]
        filename = location.split('/')[-1]
        return storage_url, container, filename

    def _verify_checksum(self, etag, checksum):
        etag_checksum = etag.strip('"')
        if etag_checksum != checksum:
            msg = ('Checksum validation failure, actual: %s, expected: %s' %
                   (etag_checksum, checksum))
            raise Exception(msg)

    def load(self, location, backup_checksum):
        """Get object from the location."""
        storage_url, container, filename = self._explodeLocation(location)

        headers, contents = self.client.get_object(container, filename,
                                                   resp_chunk_size=2 ** 16)

        if backup_checksum:
            self._verify_checksum(headers.get('etag', ''), backup_checksum)

        return contents

    def load_metadata(self, parent_location, parent_checksum):
        """Load metadata from swift."""
        if not parent_location:
            return {}

        _, container, filename = self._explodeLocation(parent_location)
        headers = self.client.head_object(container, filename)

        if parent_checksum:
            self._verify_checksum(headers.get('etag', ''), parent_checksum)

        _meta = {}
        for key, value in headers.items():
            if key.startswith('x-object-meta'):
                _meta[_get_attr(key)] = value

        return _meta

    def is_incremental_backup(self, location):
        """Check if the location is an incremental backup."""
        _, container, filename = self._explodeLocation(location)
        headers = self.client.head_object(container, filename)

        if 'x-object-meta-parent-location' in headers:
            return True

        return False

    def get_backup_lsn(self, location):
        """Get the backup LSN if exists."""
        _, container, filename = self._explodeLocation(location)
        headers = self.client.head_object(container, filename)
        return headers.get('x-object-meta-lsn')
