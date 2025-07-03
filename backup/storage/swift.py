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
import io
import json
import tempfile

from keystoneauth1.identity import v3
from keystoneauth1 import session
from oslo_config import cfg
from oslo_log import log as logging
import swiftclient
from swiftclient import exceptions as swift_exc

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


def _get_service_client(auth_url, token, tenant_id, region_name=None):
    sess = _get_user_keystone_session(auth_url, token, tenant_id)
    os_options = None
    if region_name:
        os_options = {
            'region_name': region_name
        }
    return swiftclient.Connection(session=sess,
                                  os_options=os_options,
                                  insecure=True)


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
    """Wrap the stream from the backup process and chunk it into segments.
    This class now buffers each segment to a temporary file, making it seekable
    for retry mechanisms, like the one in swiftclient.
    """

    def __init__(self, stream, container, filename, max_file_size):
        self.stream = stream
        self.container = container
        self.filename = filename
        self.max_file_size = max_file_size
        # Will be incremented to 0 in _start_new_segment
        self.file_number = 0
        # True if the entire original stream is exhausted
        self.end_of_file = False
        # tempfile.TemporaryFile for current segment
        self._current_segment_buffer = None
        self._current_segment_checksum = hashlib.md5()
        self._current_segment_length = 0
        # Current read position within _current_segment_buffer
        self._buffer_read_offset = 0
        # True when the current segment is fully read from original stream
        self._segment_fully_buffered = False
        self._prepare_for_new_segment = True

    def _start_new_segment(self):
        # Prepares for a new segment by creating a new buffer and
        #  resetting state.
        if self._current_segment_buffer:
            # Store the final checksum before closing the buffer
            self._current_segment_buffer.close()

        # Using a temporary file for buffering as segments can be large (2GB)
        self._current_segment_buffer = tempfile.TemporaryFile()
        self._current_segment_checksum = hashlib.md5()
        self._current_segment_length = 0
        # Reset read pointer for the new buffer
        self._buffer_read_offset = 0
        # # Reset flag for new segment
        self._segment_fully_buffered = False

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
        """Read data from the stream. This method buffers the current segment
        from the underlying stream to a temporary file, then serves chunks
        from that buffer. This makes the stream seekable.
        """
        # Phase 1: Ensure the current segment is fully buffered from the
        # original stream. This loop will run until the current segment's
        # data is entirely in _current_segment_buffer or the original
        # stream is exhausted.
        if self._prepare_for_new_segment:
            self._start_new_segment()
            self._prepare_for_new_segment = False

        if not self._segment_fully_buffered:
            while True:
                if (self._current_segment_length + chunk_size) > \
                        self.max_file_size:
                    self._segment_fully_buffered = True
                    LOG.info("StreamReader: Current segment %s reached max "
                             "size. Fully buffered.", self.segment)
                    break

                # Read from the original, unseekable stream
                chunk = self.stream.read(chunk_size)

                if not chunk:
                    # Original stream exhausted. Mark overall end of file.
                    self.end_of_file = True
                    self._segment_fully_buffered = True
                    LOG.info("StreamReader: Original stream exhausted. "
                             "Current segment %s fully buffered.",
                             self.segment)
                    break

                self._current_segment_buffer.write(chunk)
                self._current_segment_checksum.update(chunk)
                self._current_segment_length += len(chunk)

            # After buffering is complete for this segment, rewind the buffer
            # so that subsequent reads (by swiftclient,
            # potentially after seek) start from the beginning of the
            # buffered data.
            self._current_segment_buffer.seek(0)
            self._buffer_read_offset = 0
        # Phase 2: Serve data from the buffered temporary file
        data = self._current_segment_buffer.read(chunk_size)
        self._buffer_read_offset += len(data)
        # start new segment if the orignal stream is not exhausted
        if not data and not self.end_of_file:
            LOG.info("StreamReader: Finished serving data for segment %s. "
                     "Preparing for next.", self.segment)
            self._prepare_for_new_segment = True
            self.file_number += 1
            return b''

        # If we've reached the end of the file, just return empty
        if not data and self.end_of_file:
            return b''

        return data

    def seek(self, offset, whence=io.SEEK_SET):
        """Seek within the current segment's buffered data."""
        if not self._current_segment_buffer:
            raise io.UnsupportedOperation("StreamReader: No segment buffer "
                                          "available for seeking.")

        new_pos = self._current_segment_buffer.seek(offset, whence)
        self._buffer_read_offset = new_pos

        if new_pos > self._current_segment_length:
            raise IOError(f"StreamReader: Cannot seek beyond buffered data. "
                          f"Requested position: {new_pos}, Buffered data "
                          f"length: {self._current_segment_length}")

        return new_pos

    def tell(self):
        # Return the current position within the current segment's
        # buffered data.
        if not self._current_segment_buffer:
            return 0
        return self._buffer_read_offset

    @property
    def segment_checksum(self):
        """Returns the checksum of the *current* segment."""
        return self._current_segment_checksum.hexdigest()

    @property
    def segment_length(self):
        """Returns the length of the *current* segment."""
        return self._current_segment_length

    def release_buffer(self):
        """Manually release the current segment buffer."""
        if self._current_segment_buffer:
            self._current_segment_buffer.close()
            self._current_segment_buffer = None


class SwiftStorage(base.Storage):
    def __init__(self):
        self.client = _get_service_client(CONF.os_auth_url, CONF.os_token,
                                          CONF.os_tenant_id,
                                          region_name=CONF.os_region_name)

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
        try:
            self.client.put_container(container)
        except swift_exc.ClientException as e:
            # 409 Conflict means container already exists
            if e.http_status != 409:
                LOG.error('Failed to create container %s: %s',
                          container, str(e))
                raise

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
            segment_name = stream_reader.segment
            # This path includes the correct segment number
            path = stream_reader.segment_path

            LOG.info('Uploading segment %s.', segment_name)
            # self.client.put_object now receives a seekable stream_reader,
            # allowing swiftclient's internal retries to work on the current
            # segment.
            try:
                etag = self.client.put_object(container,
                                              segment_name,
                                              stream_reader)
            except swift_exc.ClientException as e:
                LOG.error('Swift client error uploading segment %s: %s',
                          segment_name, str(e))
                raise
            # After put_object returns, the segment_checksum and segment_length
            # properties of stream_reader refer to the segment that was just
            # uploaded.
            segment_md5 = stream_reader.segment_checksum
            current_segment_bytes = stream_reader.segment_length

            # Check each segment MD5 hash against swift etag
            if etag != segment_md5:
                msg = ('Failed to upload data segment to swift. ETAG: %(tag)s '
                       'Segment MD5: %(checksum)s.' %
                       {'tag': etag, 'checksum': segment_md5})
                raise Exception(msg)

            segment_results.append({
                'path': path,
                'etag': etag,
                'size_bytes': current_segment_bytes
            })

            swift_checksum.update(segment_md5.encode())

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
                                   headers=headers,
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
            except swift_exc.ClientException as e:
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
