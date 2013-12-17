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

from trove.guestagent.strategies.storage import base
from trove.openstack.common import log as logging
from trove.common.remote import create_swift_client
from trove.common import cfg
from trove.common import utils
from eventlet.green import subprocess

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
    def prefix(self):
        return '%s/%s_' % (self.container, self.base_filename)

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
    """Implementation of Storage Strategy for Swift """
    __strategy_name__ = 'swift'

    def __init__(self, *args, **kwargs):
        super(SwiftStorage, self).__init__(*args, **kwargs)
        self.connection = create_swift_client(self.context)

    def save(self, filename, stream):
        """Persist information from the stream to swift.

        The file is saved to the location <BACKUP_CONTAINER>/<filename>.
        The filename is defined on the backup runner manifest property
        which is typically in the format '<backup_id>.<ext>.gz'
        """

        # Create the container if it doesn't already exist
        self.connection.put_container(BACKUP_CONTAINER)

        # Swift Checksum is the checksum of the concatenated segment checksums
        swift_checksum = hashlib.md5()

        # Wrap the output of the backup process to segment it for swift
        stream_reader = StreamReader(stream, filename)

        url = self.connection.url
        # Full location where the backup manifest is stored
        location = "%s/%s/%s" % (url, BACKUP_CONTAINER, filename)

        # Read from the stream and write to the container in swift
        while not stream_reader.end_of_file:
            etag = self.connection.put_object(BACKUP_CONTAINER,
                                              stream_reader.segment,
                                              stream_reader)

            segment_checksum = stream_reader.segment_checksum.hexdigest()

            # Check each segment MD5 hash against swift etag
            # Raise an error and mark backup as failed
            if etag != segment_checksum:
                LOG.error("Error saving data segment to swift. "
                          "ETAG: %s Segment MD5: %s",
                          etag, segment_checksum)
                return False, "Error saving data to Swift!", None, location

            swift_checksum.update(segment_checksum)

        # Create the manifest file
        # We create the manifest file after all the segments have been uploaded
        # so a partial swift object file can't be downloaded; if the manifest
        # file exists then all segments have been uploaded so the whole backup
        # file can be downloaded.
        headers = {'X-Object-Manifest': stream_reader.prefix}
        # The etag returned from the manifest PUT is the checksum of the
        # manifest object (which is empty); this is not the checksum we want
        self.connection.put_object(BACKUP_CONTAINER,
                                   filename,
                                   contents='',
                                   headers=headers)

        resp = self.connection.head_object(BACKUP_CONTAINER, filename)
        # swift returns etag in double quotes
        # e.g. '"dc3b0827f276d8d78312992cc60c2c3f"'
        etag = resp['etag'].strip('"')

        # Check the checksum of the concatenated segment checksums against
        # swift manifest etag.
        # Raise an error and mark backup as failed
        final_swift_checksum = swift_checksum.hexdigest()
        if etag != final_swift_checksum:
            LOG.error(
                "Error saving data to swift. Manifest ETAG: %s Swift MD5: %s",
                etag, final_swift_checksum)
            return False, "Error saving data to Swift!", None, location

        return (True, "Successfully saved data to Swift!",
                final_swift_checksum, location)

    def _explodeLocation(self, location):
        storage_url = "/".join(location.split('/')[:-2])
        container = location.split('/')[-2]
        filename = location.split('/')[-1]
        return storage_url, container, filename

    def load(self, context, location, is_zipped, backup_checksum):
        """Restore a backup from the input stream to the restore_location """

        storage_url, container, filename = self._explodeLocation(location)

        return SwiftDownloadStream(context,
                                   auth_token=context.auth_token,
                                   storage_url=storage_url,
                                   container=container,
                                   filename=filename,
                                   is_zipped=is_zipped,
                                   backup_checksum=backup_checksum)


class SwiftDownloadStream(object):
    """Class to do the actual swift download  using the swiftclient """

    cmd = ("swift --os-auth-token=%(auth_token)s "
           "--os-storage-url=%(storage_url)s "
           "download %(container)s %(filename)s -o -")

    def __init__(self, context, **kwargs):
        self.process = None
        self.pid = None
        self.cmd = self.cmd % kwargs
        self.container = kwargs.get('container')
        self.filename = kwargs.get('filename')
        self.original_backup_checksum = kwargs.get('backup_checksum', None)
        self.swift_client = create_swift_client(context)

    def __enter__(self):
        """Start up the process"""
        self.run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Clean up everything."""
        if exc_type is None:
            utils.raise_if_process_errored(self.process, DownloadError)

        # Make sure to terminate the process
        try:
            self.process.terminate()
        except OSError:
            # Already stopped
            pass

    def read(self, *args, **kwargs):
        return self.process.stdout.read(*args, **kwargs)

    def run(self):
        if CONF.verify_swift_checksum_on_restore:
            # Right before downloading swift object lets check that the current
            # swift object checksum matches the original backup checksum
            self._verify_checksum()
        self._run_download_cmd()

    def _verify_checksum(self):
        if self.original_backup_checksum:
            resp = self.swift_client.head_object(self.container, self.filename)
            current_swift_checksum = resp['etag'].strip('"')
            if current_swift_checksum != self.original_backup_checksum:
                raise SwiftDownloadIntegrityError("Original backup checksum "
                                                  "does not match current "
                                                  "checksum.")

    def _run_download_cmd(self):
        self.process = subprocess.Popen(self.cmd, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        self.pid = self.process.pid
