# Copyright 2015 Tesora Inc.
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

import enum
import hashlib
import os
from requests.exceptions import ConnectionError

from oslo_log import log as logging
from swiftclient.client import ClientException

from trove.common import cfg
from trove.common import clients
from trove.common import exception
from trove.common.i18n import _
from trove.common import stream_codecs
from trove.common import timeutils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class LogType(enum.Enum):
    """Represent the type of the log object."""

    # System logs.  These are always enabled.
    SYS = 1

    # User logs.  These can be enabled or disabled.
    USER = 2


class LogStatus(enum.Enum):
    """Represent the status of the log object."""

    # The log is disabled and potentially no data is being written to
    # the corresponding log file
    Disabled = 1

    # Logging is on, but no determination has been made about data availability
    Enabled = 2

    # Logging is on, but no log data is available to publish
    Unavailable = 3

    # Logging is on and data is available to be published
    Ready = 4

    # Logging is on and all data has been published
    Published = 5

    # Logging is on and some data has been published
    Partial = 6

    # Log file has been rotated, so next publish will discard log first
    Rotated = 7

    # Waiting for a datastore restart to begin logging
    Restart_Required = 8

    # Now that restart has completed, regular status can be reported again
    # This is an internal status
    Restart_Completed = 9


class GuestLog(object):

    MF_FILE_SUFFIX = '_metafile'
    MF_LABEL_LOG_NAME = 'log_name'
    MF_LABEL_LOG_TYPE = 'log_type'
    MF_LABEL_LOG_FILE = 'log_file'
    MF_LABEL_LOG_SIZE = 'log_size'
    MF_LABEL_LOG_HEADER = 'log_header_digest'

    def __init__(self, log_context, log_name, log_type, log_user, log_file,
                 log_exposed):
        self._context = log_context
        self._name = log_name
        self._type = log_type
        self._user = log_user
        self._file = log_file
        self._exposed = log_exposed
        self._size = None
        self._published_size = None
        self._header_digest = 'abc'
        self._published_header_digest = None
        self._status = None
        self._cached_context = None
        self._cached_swift_client = None
        self._enabled = log_type == LogType.SYS
        self._file_readable = False
        self._container_name = None
        self._codec = stream_codecs.JsonCodec()

        self._set_status(self._type == LogType.USER,
                         LogStatus.Disabled, LogStatus.Enabled)

        # The directory should already exist - make sure we have access to it
        log_dir = os.path.dirname(self._file)
        operating_system.chmod(
            log_dir, FileMode.ADD_GRP_RX_OTH_RX, as_root=True)

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, context):
        self._context = context

    @property
    def type(self):
        return self._type

    @property
    def swift_client(self):
        if not self._cached_swift_client or (
                self._cached_context != self.context):
            self._cached_swift_client = clients.swift_client(self.context)
            self._cached_context = self.context
        return self._cached_swift_client

    @property
    def exposed(self):
        return self._exposed or self.context.is_admin

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        self._enabled = enabled

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        # Keep the status in Restart_Required until we're set
        # to Restart_Completed
        if (self.status != LogStatus.Restart_Required or
                (self.status == LogStatus.Restart_Required and
                 status == LogStatus.Restart_Completed)):
            self._status = status
            LOG.debug("Log status for '%(name)s' set to %(status)s",
                      {'name': self._name, 'status': status})
        else:
            LOG.debug("Log status for '%(name)s' *not* set to %(status)s "
                      "(currently %(current_status)s)",
                      {'name': self._name, 'status': status,
                       'current_status': self.status})

    def get_container_name(self, force=False):
        if not self._container_name or force:
            container_name = CONF.guest_log_container_name
            try:
                self.swift_client.get_container(container_name, prefix='dummy')
            except ClientException as ex:
                if ex.http_status == 404:
                    LOG.debug("Container '%s' not found; creating now",
                              container_name)
                    self.swift_client.put_container(
                        container_name, headers=self._get_headers())
                else:
                    LOG.exception("Could not retrieve container '%s'",
                                  container_name)
                    raise
            self._container_name = container_name
        return self._container_name

    def _set_status(self, use_first, first_status, second_status):
        if use_first:
            self.status = first_status
        else:
            self.status = second_status

    def show(self):
        if self.exposed:
            self._refresh_details()
            container_name = 'None'
            prefix = 'None'
            if self._published_size:
                container_name = self.get_container_name()
                prefix = self._object_prefix()
            pending = self._size - self._published_size
            if self.status == LogStatus.Rotated:
                pending = self._size
            return {
                'name': self._name,
                'type': self._type.name,
                'status': self.status.name.replace('_', ' '),
                'published': self._published_size,
                'pending': pending,
                'container': container_name,
                'prefix': prefix,
                'metafile': self._metafile_name()
            }
        else:
            raise exception.LogAccessForbidden(action='show', log=self._name)

    def _refresh_details(self):

        if self._published_size is None:
            # Initializing, so get all the values
            try:
                meta_details = self._get_meta_details()
                self._published_size = int(
                    meta_details[self.MF_LABEL_LOG_SIZE])
                self._published_header_digest = (
                    meta_details[self.MF_LABEL_LOG_HEADER])
            except ClientException as ex:
                if ex.http_status == 404:
                    LOG.debug("No published metadata found for log '%s'",
                              self._name)
                    self._published_size = 0
                else:
                    LOG.exception("Could not get meta details for log '%s'",
                                  self._name)
                    raise
            except ConnectionError as e:
                # A bad endpoint will cause a ConnectionError
                # This exception contains another exception that we want
                exc = e.args[0]
                raise exc

        self._update_details()
        LOG.debug("Log size for '%(name)s' set to %(size)d "
                  "(published %(published)d)",
                  {'name': self._name, 'size': self._size,
                   'published': self._published_size})

    def _update_details(self):
        # Make sure we can read the file
        if not self._file_readable or not os.access(self._file, os.R_OK):
            if not os.access(self._file, os.R_OK):
                if operating_system.exists(self._file, as_root=True):
                    operating_system.chmod(
                        self._file, FileMode.ADD_ALL_R, as_root=True)
            self._file_readable = True

        if os.path.isfile(self._file):
            logstat = os.stat(self._file)
            self._size = logstat.st_size
            self._update_log_header_digest(self._file)

            if self._log_rotated():
                self.status = LogStatus.Rotated
            # See if we have stuff to publish
            elif logstat.st_size > self._published_size:
                self._set_status(self._published_size,
                                 LogStatus.Partial, LogStatus.Ready)
            # We've published everything so far
            elif logstat.st_size == self._published_size:
                self._set_status(self._published_size,
                                 LogStatus.Published, LogStatus.Enabled)
            # We've already handled this case (log rotated) so what gives?
            else:
                raise Exception(_("Bug in _log_rotated ?"))
        else:
            self._published_size = 0
            self._size = 0

        if not self._size or not self.enabled:
            user_status = LogStatus.Disabled
            if self.enabled:
                user_status = LogStatus.Enabled
            self._set_status(self._type == LogType.USER,
                             user_status, LogStatus.Unavailable)

    def _log_rotated(self):
        """If the file is smaller than the last reported size
        or the first line hash is different, we can probably assume
        the file changed under our nose.
        """
        if (self._published_size > 0 and
                (self._size < self._published_size or
                 self._published_header_digest != self._header_digest)):
            return True

    def _update_log_header_digest(self, log_file):
        with open(log_file, 'rb') as log:
            self._header_digest = hashlib.md5(log.readline()).hexdigest()

    def _get_headers(self):
        return {'X-Delete-After': str(CONF.guest_log_expiry)}

    def publish_log(self):
        if self.exposed:
            if self._log_rotated():
                LOG.debug("Log file rotation detected for '%s' - "
                          "discarding old log", self._name)
                self._delete_log_components()
            if os.path.isfile(self._file):
                self._publish_to_container(self._file)
            else:
                raise RuntimeError(_(
                    "Cannot publish log file '%s' as it does not exist.") %
                    self._file)
            return self.show()
        else:
            raise exception.LogAccessForbidden(
                action='publish', log=self._name)

    def discard_log(self):
        if self.exposed:
            self._delete_log_components()
            return self.show()
        else:
            raise exception.LogAccessForbidden(
                action='discard', log=self._name)

    def _delete_log_components(self):
        container_name = self.get_container_name(force=True)
        prefix = self._object_prefix()
        swift_files = [swift_file['name']
                       for swift_file in self.swift_client.get_container(
                       container_name, prefix=prefix)[1]]
        swift_files.append(self._metafile_name())
        for swift_file in swift_files:
            self.swift_client.delete_object(container_name, swift_file)
        self._set_status(self._type == LogType.USER,
                         LogStatus.Disabled, LogStatus.Enabled)
        self._published_size = 0

    def _publish_to_container(self, log_filename):
        log_component, log_lines = '', 0
        chunk_size = CONF.guest_log_limit
        container_name = self.get_container_name(force=True)

        def _read_chunk(f):
            while True:
                current_chunk = f.read(chunk_size)
                if not current_chunk:
                    break
                yield current_chunk

        def _write_log_component():
            object_headers.update({'x-object-meta-lines': str(log_lines)})
            component_name = '%s%s' % (self._object_prefix(),
                                       self._object_name())
            self.swift_client.put_object(container_name,
                                         component_name, log_component,
                                         headers=object_headers)
            self._published_size = (
                self._published_size + len(log_component))
            self._published_header_digest = self._header_digest

        self._refresh_details()
        self._put_meta_details()
        object_headers = self._get_headers()
        with open(log_filename, 'r') as log:
            LOG.debug("seeking to %s", self._published_size)
            log.seek(self._published_size)
            for chunk in _read_chunk(log):
                for log_line in chunk.splitlines():
                    if len(log_component) + len(log_line) > chunk_size:
                        _write_log_component()
                        log_component, log_lines = '', 0
                    log_component = log_component + log_line + '\n'
                    log_lines += 1
        if log_lines > 0:
            _write_log_component()
        self._put_meta_details()

    def _put_meta_details(self):
        metafile_name = self._metafile_name()
        metafile_details = {
            self.MF_LABEL_LOG_NAME: self._name,
            self.MF_LABEL_LOG_TYPE: self._type.name,
            self.MF_LABEL_LOG_FILE: self._file,
            self.MF_LABEL_LOG_SIZE: self._published_size,
            self.MF_LABEL_LOG_HEADER: self._header_digest,
        }
        container_name = self.get_container_name()
        self.swift_client.put_object(container_name, metafile_name,
                                     self._codec.serialize(metafile_details),
                                     headers=self._get_headers())
        LOG.debug("_put_meta_details has published log size as %s",
                  self._published_size)

    def _metafile_name(self):
        return self._object_prefix().rstrip('/') + '_metafile'

    def _object_prefix(self):
        return '%(instance_id)s/%(datastore)s-%(log)s/' % {
            'instance_id': CONF.guest_id,
            'datastore': CONF.datastore_manager,
            'log': self._name}

    def _object_name(self):
        return 'log-%s' % str(timeutils.utcnow()).replace(' ', 'T')

    def _get_meta_details(self):
        LOG.debug("Getting meta details for '%s'", self._name)
        metafile_name = self._metafile_name()
        container_name = self.get_container_name()
        headers, metafile_details = self.swift_client.get_object(
            container_name, metafile_name)
        LOG.debug("Found meta details for '%s'", self._name)
        return self._codec.deserialize(metafile_details)
