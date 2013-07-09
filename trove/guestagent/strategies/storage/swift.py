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

from trove.guestagent.strategies.storage import base
from trove.openstack.common import log as logging
from trove.common.remote import create_swift_client
from trove.common import utils
from eventlet.green import subprocess
import zlib

LOG = logging.getLogger(__name__)


class DownloadError(Exception):
    """Error running the Swift Download Command."""


class SwiftStorage(base.Storage):
    """ Implementation of Storage Strategy for Swift """
    __strategy_name__ = 'swift'

    def __init__(self, context):
        super(SwiftStorage, self).__init__()
        self.connection = create_swift_client(context)

    def set_container(self, ):
        """ Set the container to store to.  """
        """ This creates the container if it doesn't exist.  """

    def save(self, save_location, stream):
        """ Persist information from the stream """

        # Create the container (save_location) if it doesn't already exist
        self.container_name = save_location
        self.segments_container_name = stream.manifest + "_segments"
        self.connection.put_container(self.container_name)
        self.connection.put_container(self.segments_container_name)

        # Read from the stream and write to the container in swift
        while not stream.end_of_file:
            segment = stream.segment
            etag = self.connection.put_object(self.segments_container_name,
                                              segment,
                                              stream)

            # Check each segment MD5 hash against swift etag
            # Raise an error and mark backup as failed
            if etag != stream.schecksum.hexdigest():
                print("%s %s" % (etag, stream.schecksum.hexdigest()))
                return (False, "Error saving data to Swift!", None, None)

            checksum = stream.checksum.hexdigest()
            url = self.connection.url
            location = "%s/%s/%s" % (url, self.container_name, stream.manifest)

            # Create the manifest file
            headers = {
                'X-Object-Manifest':
                self.segments_container_name + "/" + stream.filename}
            self.connection.put_object(self.container_name,
                                       stream.manifest,
                                       contents='',
                                       headers=headers)

            return (True, "Successfully saved data to Swift!",
                    checksum, location)

    def _explodeLocation(self, location):
        storage_url = "/".join(location.split('/')[:-2])
        container = location.split('/')[-2]
        filename = location.split('/')[-1]
        return storage_url, container, filename

    def load(self, context, location, is_zipped):
        """ Restore a backup from the input stream to the restore_location """

        storage_url, container, filename = self._explodeLocation(location)

        return SwiftDownloadStream(auth_token=context.auth_token,
                                   storage_url=storage_url,
                                   container=container,
                                   filename=filename,
                                   is_zipped=is_zipped)


class SwiftDownloadStream(object):
    """ Class to do the actual swift download  using the swiftclient """

    cmd = ("swift --os-auth-token=%(auth_token)s "
           "--os-storage-url=%(storage_url)s "
           "download %(container)s %(filename)s -o -")

    def __init__(self, **kwargs):
        self.process = None
        self.pid = None
        self.cmd = self.cmd % kwargs

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
        self.process = subprocess.Popen(self.cmd, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        self.pid = self.process.pid
