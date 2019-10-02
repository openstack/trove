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

import hashlib
import json

from oslo_log import log as logging
import six

from trove.common import cfg
from trove.common.clients import create_swift_client
from trove.common.i18n import _
from trove.common.strategies.storage import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

CHUNK_SIZE = CONF.backup_chunk_size
MAX_FILE_SIZE = CONF.backup_segment_max_size
BACKUP_CONTAINER = CONF.backup_swift_container


class DownloadError(Exception):
    """Error running the Swift Download Command."""


class SwiftDownloadIntegrityError(Exception):
    """Integrity error while running the Swift Download Command."""


class StreamReader(object):
    """Wrap the stream from the backup process and chunk it into segements."""

    def __init__(self, stream, filename, max_file_size=MAX_FILE_SIZE):
        self.stream = stream
        self.filename = filename
        self.container = BACKUP_CONTAINER
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

    def read(self, chunk_size=CHUNK_SIZE):
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
    """Implementation of Storage Strategy for Swift."""
    __strategy_name__ = 'swift'

    def __init__(self, *args, **kwargs):
        super(SwiftStorage, self).__init__(*args, **kwargs)
        self.connection = create_swift_client(self.context)

    def save(self, filename, stream, metadata=None):
        """Persist information from the stream to swift.

        The file is saved to the location <BACKUP_CONTAINER>/<filename>.
        It will be a Swift Static Large Object (SLO).
        The filename is defined on the backup runner manifest property
        which is typically in the format '<backup_id>.<ext>.gz'
        """

        LOG.info('Saving %(filename)s to %(container)s in swift.',
                 {'filename': filename, 'container': BACKUP_CONTAINER})

        # Create the container if it doesn't already exist
        LOG.debug('Creating container %s.', BACKUP_CONTAINER)
        self.connection.put_container(BACKUP_CONTAINER)

        # Swift Checksum is the checksum of the concatenated segment checksums
        swift_checksum = hashlib.md5()

        # Wrap the output of the backup process to segment it for swift
        stream_reader = StreamReader(stream, filename, MAX_FILE_SIZE)
        LOG.debug('Using segment size %s', stream_reader.max_file_size)

        url = self.connection.url
        # Full location where the backup manifest is stored
        location = "%s/%s/%s" % (url, BACKUP_CONTAINER, filename)

        # Information about each segment upload job
        segment_results = []

        # Read from the stream and write to the container in swift
        while not stream_reader.end_of_file:
            LOG.debug('Saving segment %s.', stream_reader.segment)
            path = stream_reader.segment_path
            etag = self.connection.put_object(BACKUP_CONTAINER,
                                              stream_reader.segment,
                                              stream_reader)

            segment_checksum = stream_reader.segment_checksum.hexdigest()

            # Check each segment MD5 hash against swift etag
            # Raise an error and mark backup as failed
            if etag != segment_checksum:
                LOG.error("Error saving data segment to swift. "
                          "ETAG: %(tag)s Segment MD5: %(checksum)s.",
                          {'tag': etag, 'checksum': segment_checksum})
                return False, "Error saving data to Swift!", None, location

            segment_results.append({
                'path': path,
                'etag': etag,
                'size_bytes': stream_reader.segment_length
            })

            if six.PY3:
                swift_checksum.update(segment_checksum.encode())
            else:
                swift_checksum.update(segment_checksum)

        # All segments uploaded.
        num_segments = len(segment_results)
        LOG.debug('File uploaded in %s segments.', num_segments)

        # An SLO will be generated if the backup was more than one segment in
        # length.
        large_object = num_segments > 1

        # Meta data is stored as headers
        if metadata is None:
            metadata = {}
        metadata.update(stream.metadata())
        headers = {}
        for key, value in metadata.items():
            headers[self._set_attr(key)] = value

        LOG.debug('Metadata headers: %s', str(headers))
        if large_object:
            LOG.info('Creating the manifest file.')
            manifest_data = json.dumps(segment_results)
            LOG.debug('Manifest contents: %s', manifest_data)
            # The etag returned from the manifest PUT is the checksum of the
            # manifest object (which is empty); this is not the checksum we
            # want.
            self.connection.put_object(BACKUP_CONTAINER,
                                       filename,
                                       manifest_data,
                                       query_string='multipart-manifest=put')

            # Validation checksum is the Swift Checksum
            final_swift_checksum = swift_checksum.hexdigest()
        else:
            LOG.info('Backup fits in a single segment. Moving segment '
                     '%(segment)s to %(filename)s.',
                     {'segment': stream_reader.first_segment,
                      'filename': filename})
            segment_result = segment_results[0]
            # Just rename it via a special put copy.
            headers['X-Copy-From'] = segment_result['path']
            self.connection.put_object(BACKUP_CONTAINER,
                                       filename, '',
                                       headers=headers)
            # Delete the old segment file that was copied
            LOG.debug('Deleting the old segment file %s.',
                      stream_reader.first_segment)
            self.connection.delete_object(BACKUP_CONTAINER,
                                          stream_reader.first_segment)
            final_swift_checksum = segment_result['etag']

        # Validate the object by comparing checksums
        # Get the checksum according to Swift
        resp = self.connection.head_object(BACKUP_CONTAINER, filename)
        # swift returns etag in double quotes
        # e.g. '"dc3b0827f276d8d78312992cc60c2c3f"'
        etag = resp['etag'].strip('"')

        # Raise an error and mark backup as failed
        if etag != final_swift_checksum:
            LOG.error(
                ("Error saving data to swift. Manifest "
                 "ETAG: %(tag)s Swift MD5: %(checksum)s"),
                {'tag': etag, 'checksum': final_swift_checksum})
            return False, "Error saving data to Swift!", None, location

        return (True, "Successfully saved data to Swift!",
                final_swift_checksum, location)

    def _explodeLocation(self, location):
        storage_url = "/".join(location.split('/')[:-2])
        container = location.split('/')[-2]
        filename = location.split('/')[-1]
        return storage_url, container, filename

    def _verify_checksum(self, etag, checksum):
        etag_checksum = etag.strip('"')
        if etag_checksum != checksum:
            log_fmt = ("Original checksum: %(original)s does not match"
                       " the current checksum: %(current)s")
            exc_fmt = _("Original checksum: %(original)s does not match"
                        " the current checksum: %(current)s")
            msg_content = {
                'original': etag_checksum,
                'current': checksum}
            LOG.error(log_fmt, msg_content)
            raise SwiftDownloadIntegrityError(exc_fmt % msg_content)
        return True

    def load(self, location, backup_checksum):
        """Restore a backup from the input stream to the restore_location."""
        storage_url, container, filename = self._explodeLocation(location)

        headers, info = self.connection.get_object(container, filename,
                                                   resp_chunk_size=CHUNK_SIZE)

        if CONF.verify_swift_checksum_on_restore:
            self._verify_checksum(headers.get('etag', ''), backup_checksum)

        return info

    def _get_attr(self, original):
        """Get a friendly name from an object header key."""
        key = original.replace('-', '_')
        key = key.replace('x_object_meta_', '')
        return key

    def _set_attr(self, original):
        """Return a swift friendly header key."""
        key = original.replace('_', '-')
        return 'X-Object-Meta-%s' % key

    def load_metadata(self, location, backup_checksum):
        """Load metadata from swift."""

        storage_url, container, filename = self._explodeLocation(location)

        headers = self.connection.head_object(container, filename)

        if CONF.verify_swift_checksum_on_restore:
            self._verify_checksum(headers.get('etag', ''), backup_checksum)

        _meta = {}
        for key, value in headers.items():
            if key.startswith('x-object-meta'):
                _meta[self._get_attr(key)] = value

        return _meta

    def save_metadata(self, location, metadata={}):
        """Save metadata to a swift object."""

        storage_url, container, filename = self._explodeLocation(location)

        headers = {}
        for key, value in metadata.items():
            headers[self._set_attr(key)] = value

        LOG.info("Writing metadata: %s", str(headers))
        self.connection.post_object(container, filename, headers=headers)
