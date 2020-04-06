# Copyright (c) 2011 OpenStack Foundation
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

from functools import reduce
import inspect
import operator
import os
import pwd
import re
import stat
import tempfile

from oslo_concurrency.processutils import UnknownArgumentError

from trove.common import exception
from trove.common import utils
from trove.common.i18n import _
from trove.common.stream_codecs import IdentityCodec

REDHAT = 'redhat'
DEBIAN = 'debian'
SUSE = 'suse'


def read_file(path, codec=IdentityCodec(), as_root=False, decode=True):
    """
    Read a file into a Python data structure
    digestible by 'write_file'.

    :param path:            Path to the read config file.
    :type path:             string

    :param codec:           A codec used to transform the data.
    :type codec:            StreamCodec

    :param as_root:         Execute as root.
    :type as_root:          boolean

    :param decode:          Should the codec decode the data.
    :type decode:           boolean

    :returns:               A dictionary of key-value pairs.

    :raises:                :class:`UnprocessableEntity` if file doesn't exist.
    :raises:                :class:`UnprocessableEntity` if codec not given.
    """
    if path and exists(path, is_directory=False, as_root=as_root):
        if decode:
            open_flag = 'r'
            convert_func = codec.deserialize
        else:
            open_flag = 'rb'
            convert_func = codec.serialize

        if as_root:
            return _read_file_as_root(path, open_flag, convert_func)

        with open(path, open_flag) as fp:
            return convert_func(fp.read())

    raise exception.UnprocessableEntity(_("File does not exist: %s") % path)


def exists(path, is_directory=False, as_root=False):
    """Check a given path exists.

    :param path                Path to be checked.
    :type path                 string

    :param is_directory:       Check that the path exists and is a directory.
                               Check for a regular file otherwise.
    :type is_directory:        boolean

    :param as_root:            Execute as root.
    :type as_root:             boolean
    """

    found = (not is_directory and os.path.isfile(path) or
             (is_directory and os.path.isdir(path)))

    # Only check as root if we can't see it as the regular user, since
    # this is more expensive
    if not found and as_root:
        test_flag = '-d' if is_directory else '-f'
        cmd = 'test %s %s && echo 1 || echo 0' % (test_flag, path)
        stdout, _ = utils.execute_with_timeout(
            cmd, shell=True, check_exit_code=False,
            run_as_root=True, root_helper='sudo')
        found = bool(int(stdout))

    return found


def find_executable(executable, path=None):
    """Finds a location of an executable in the locations listed in 'path'

    :param executable          File to search.
    :type executable           string

    :param path                Lookup directories separated by a path
                               separartor.
    :type path                 string
    """
    if path is None:
        path = os.environ.get('PATH', os.defpath)
    dirs = path.split(os.pathsep)
    for directory in dirs:
        exec_path = os.path.join(directory, executable)
        if os.path.isfile(exec_path) and os.access(exec_path, os.X_OK):
            return exec_path
    return None


def _read_file_as_root(path, open_flag, convert_func):
    """Read a file as root.

    :param path                Path to the written file.
    :type path                 string

    :param open_flag:          The flag for opening a file
    :type open_flag:           string

    :param convert_func:       The function for converting data.
    :type convert_func:        callable
    """
    with tempfile.NamedTemporaryFile(open_flag) as fp:
        copy(path, fp.name, force=True, dereference=True, as_root=True)
        chmod(fp.name, FileMode.ADD_READ_ALL(), as_root=True)
        return convert_func(fp.read())


def write_file(path, data, codec=IdentityCodec(), as_root=False, encode=True):
    """Write data into file using a given codec.
    Overwrite any existing contents.
    The written file can be read back into its original
    form by 'read_file'.

    :param path                Path to the written config file.
    :type path                 string

    :param data:               An object representing the file contents.
    :type data:                object

    :param codec:              A codec used to transform the data.
    :type codec:               StreamCodec

    :param as_root:            Execute as root.
    :type as_root:             boolean

    :param encode:             Should the codec encode the data.
    :type encode:              boolean

    :raises:                   :class:`UnprocessableEntity` if path not given.
    """
    if path:
        if encode:
            open_flag = 'w'
            convert_func = codec.serialize
        else:
            open_flag = 'wb'
            convert_func = codec.deserialize

        if as_root:
            _write_file_as_root(path, data, open_flag, convert_func)
        else:
            with open(path, open_flag) as fp:
                fp.write(convert_func(data))
                fp.flush()
    else:
        raise exception.UnprocessableEntity(_("Invalid path: %s") % path)


def _write_file_as_root(path, data, open_flag, convert_func):
    """Write a file as root. Overwrite any existing contents.

    :param path                Path to the written file.
    :type path                 string

    :param data:               An object representing the file contents.
    :type data:                StreamCodec

    :param open_flag:          The flag for opening a file
    :type open_flag:           string

    :param convert_func:       The function for converting data.
    :type convert_func:        callable
    """
    # The files gets removed automatically once the managing object goes
    # out of scope.
    with tempfile.NamedTemporaryFile(open_flag, delete=False) as fp:
        fp.write(convert_func(data))
        fp.flush()
        fp.close()  # Release the resource before proceeding.
        copy(fp.name, path, force=True, as_root=True)


class FileMode(object):
    """
    Represent file permissions (or 'modes') that can be applied on a filesystem
    path by functions such as 'chmod'. The way the modes get applied
    is generally controlled by the operation ('reset', 'add', 'remove')
    group to which they belong.
    All modes are represented as octal numbers. Modes are combined in a
    'bitwise OR' (|) operation.
    Multiple modes belonging to a single operation are combined
    into a net value for that operation which can be retrieved by one of the
    'get_*_mode' methods.
    Objects of this class are compared by the net values of their
    individual operations.

    :seealso: chmod

    :param reset:            List of (octal) modes that will be set,
                             other bits will be cleared.
    :type reset:             list

    :param add:              List of (octal) modes that will be added to the
                             current mode.
    :type add:               list

    :param remove:           List of (octal) modes that will be removed from
                             the current mode.
    :type remove:            list
    """

    @classmethod
    def SET_ALL_RWX(cls):
        return cls(reset=[stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO])  # =0777

    @classmethod
    def SET_FULL(cls):
        return cls.SET_ALL_RWX()

    @classmethod
    def SET_GRP_RW_OTH_R(cls):
        return cls(reset=[stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH])  # =0064

    @classmethod
    def SET_USR_RO(cls):
        return cls(reset=[stat.S_IRUSR])  # =0400

    @classmethod
    def SET_USR_RW(cls):
        return cls(reset=[stat.S_IRUSR | stat.S_IWUSR])  # =0600

    @classmethod
    def SET_USR_RWX(cls):
        return cls(reset=[stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR])  # =0700

    @classmethod
    def ADD_ALL_R(cls):
        return cls(add=[stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH])  # +0444

    @classmethod
    def ADD_READ_ALL(cls):
        return cls.ADD_ALL_R()

    @classmethod
    def ADD_USR_RW_GRP_RW(cls):
        return cls(add=[stat.S_IRUSR | stat.S_IWUSR |
                        stat.S_IRGRP | stat.S_IWGRP])  # +0660

    @classmethod
    def ADD_USR_RW_GRP_RW_OTH_R(cls):
        return cls(add=[stat.S_IRUSR | stat.S_IWUSR |
                        stat.S_IRGRP | stat.S_IWGRP |
                        stat.S_IROTH])  # +0664

    @classmethod
    def ADD_GRP_RW(cls):
        return cls(add=[stat.S_IRGRP | stat.S_IWGRP])  # +0060

    @classmethod
    def ADD_GRP_RX(cls):
        return cls(add=[stat.S_IRGRP | stat.S_IXGRP])  # +0050

    @classmethod
    def ADD_GRP_RX_OTH_RX(cls):
        return cls(add=[stat.S_IRGRP | stat.S_IXGRP |
                        stat.S_IROTH | stat.S_IXOTH])  # +0055

    def __init__(self, reset=None, add=None, remove=None):
        self._reset = list(reset) if reset is not None else []
        self._add = list(add) if add is not None else []
        self._remove = list(remove) if remove is not None else []

    def get_reset_mode(self):
        """Get the net (combined) mode that will be set.
        """
        return self._combine_modes(self._reset)

    def get_add_mode(self):
        """Get the net (combined) mode that will be added.
        """
        return self._combine_modes(self._add)

    def get_remove_mode(self):
        """Get the net (combined) mode that will be removed.
        """
        return self._combine_modes(self._remove)

    def _combine_modes(self, modes):
        return reduce(operator.or_, modes) if modes else None

    def has_any(self):
        """Check if any modes are specified.
        """
        return bool(self._reset or self._add or self._remove)

    def __hash__(self):
        return hash((self.get_reset_mode(),
                     self.get_add_mode(),
                     self.get_remove_mode()))

    def __eq__(self, other):
        if other and isinstance(other, FileMode):
            if other is self:
                return True

            return (other.get_reset_mode() == self.get_reset_mode() and
                    other.get_add_mode() == self.get_add_mode() and
                    other.get_remove_mode() == self.get_remove_mode())

        return False

    def __repr__(self):
        args = []
        if self._reset:
            args.append('reset=[{:03o}]'.format(self.get_reset_mode()))
        if self._add:
            args.append('add=[{:03o}]'.format(self.get_add_mode()))
        if self._remove:
            args.append('remove=[{:03o}]'.format(self.get_remove_mode()))

        return 'Modes({:s})'.format(', '.join(args))


def get_os():
    if os.path.isfile("/etc/redhat-release"):
        return REDHAT
    elif os.path.isfile("/etc/SuSE-release"):
        return SUSE
    else:
        return DEBIAN


def file_discovery(file_candidates):
    for file in file_candidates:
        if os.path.isfile(file):
            return file
    return ''


def start_service(service_candidates, **kwargs):
    _execute_service_command(service_candidates, 'cmd_start', **kwargs)


def stop_service(service_candidates, **kwargs):
    _execute_service_command(service_candidates, 'cmd_stop', **kwargs)


def enable_service_on_boot(service_candidates, **kwargs):
    _execute_service_command(service_candidates, 'cmd_enable', **kwargs)


def disable_service_on_boot(service_candidates, **kwargs):
    _execute_service_command(service_candidates, 'cmd_disable', **kwargs)


def _execute_service_command(service_candidates, command_key, **kwargs):
    """
    :param service_candidates        List of possible system service names.
    :type service_candidates         list

    :param command_key               One of the actions returned by
                                     'service_discovery'.
    :type command_key                string

    :param timeout:                  Number of seconds if specified,
                                     default if not.
                                     There is no timeout if set to None.
    :type timeout:                   integer

    :raises:          :class:`UnknownArgumentError` if passed unknown args.
    :raises:          :class:`UnprocessableEntity` if no candidate names given.
    :raises:          :class:`RuntimeError` if command not found.
    """

    exec_args = {}
    if 'timeout' in kwargs:
        exec_args['timeout'] = kwargs.pop('timeout')

    if kwargs:
        raise UnknownArgumentError(_("Got unknown keyword args: %r") % kwargs)

    if service_candidates:
        service = service_discovery(service_candidates)
        if command_key in service:
            utils.execute_with_timeout(service[command_key], shell=True,
                                       **exec_args)
        else:
            raise RuntimeError(_("Service control command not available: %s")
                               % command_key)
    else:
        raise exception.UnprocessableEntity(_("Candidate service names not "
                                              "specified."))


def service_discovery(service_candidates):
    """
    This function discovers how to start, stop, enable and disable services
    in the current environment. "service_candidates" is an array with possible
    system service names. Works for upstart, systemd, sysvinit.
    """
    result = {}
    for service in service_candidates:
        result['service'] = service
        # check upstart
        if os.path.isfile("/etc/init/%s.conf" % service):
            result['type'] = 'upstart'
            # upstart returns error code when service already started/stopped
            result['cmd_start'] = "sudo start %s || true" % service
            result['cmd_stop'] = "sudo stop %s || true" % service
            result['cmd_enable'] = ("sudo sed -i '/^manual$/d' "
                                    "/etc/init/%s.conf" % service)
            result['cmd_disable'] = ("sudo sh -c 'echo manual >> "
                                     "/etc/init/%s.conf'" % service)
            break
        # check sysvinit
        if os.path.isfile("/etc/init.d/%s" % service):
            result['type'] = 'sysvinit'
            result['cmd_start'] = "sudo service %s start" % service
            result['cmd_stop'] = "sudo service %s stop" % service
            if os.path.isfile("/usr/sbin/update-rc.d"):
                result['cmd_enable'] = "sudo update-rc.d %s defaults; sudo " \
                                       "update-rc.d %s enable" % (service,
                                                                  service)
                result['cmd_disable'] = "sudo update-rc.d %s defaults; sudo " \
                                        "update-rc.d %s disable" % (service,
                                                                    service)
            elif os.path.isfile("/sbin/chkconfig"):
                result['cmd_enable'] = "sudo chkconfig %s on" % service
                result['cmd_disable'] = "sudo chkconfig %s off" % service
            break
        # check systemd
        service_path = "/lib/systemd/system/%s.service" % service
        if os.path.isfile(service_path):
            result['type'] = 'systemd'
            result['cmd_start'] = "sudo systemctl start %s" % service
            result['cmd_stop'] = "sudo systemctl stop %s" % service

            # currently "systemctl enable" doesn't work for symlinked units
            # as described in https://bugzilla.redhat.com/1014311, therefore
            # replacing a symlink with its real path
            if os.path.islink(service_path):
                real_path = os.path.realpath(service_path)
                unit_file_name = os.path.basename(real_path)
                result['cmd_enable'] = ("sudo systemctl enable %s" %
                                        unit_file_name)
                result['cmd_disable'] = ("sudo systemctl disable %s" %
                                         unit_file_name)
            else:
                result['cmd_enable'] = "sudo systemctl enable %s" % service
                result['cmd_disable'] = "sudo systemctl disable %s" % service
            break

    return result


def _execute_shell_cmd(cmd, options, *args, **kwargs):
    """Execute a given shell command passing it
    given options (flags) and arguments.

    Takes optional keyword arguments:
    :param as_root:        Execute as root.
    :type as_root:         boolean

    :param timeout:        Number of seconds if specified,
                           default if not.
                           There is no timeout if set to None.
    :type timeout:         integer

    :raises:               class:`UnknownArgumentError` if passed unknown args.
    """

    exec_args = {}
    if kwargs.pop('as_root', False):
        exec_args['run_as_root'] = True
        exec_args['root_helper'] = 'sudo'

    if 'timeout' in kwargs:
        exec_args['timeout'] = kwargs.pop('timeout')

    exec_args['shell'] = kwargs.pop('shell', False)

    if kwargs:
        raise UnknownArgumentError(_("Got unknown keyword args: %r") % kwargs)

    cmd_flags = _build_command_options(options)
    cmd_args = cmd_flags + list(args)
    stdout, stderr = utils.execute_with_timeout(cmd, *cmd_args, **exec_args)
    return stdout


def create_directory(dir_path, user=None, group=None, force=True, **kwargs):
    """Create a given directory and update its ownership
    (recursively) to the given user and group if any.

    seealso:: _execute_shell_cmd for valid optional keyword arguments.

    :param dir_path:        Path to the created directory.
    :type dir_path:         string

    :param user:            Owner.
    :type user:             string

    :param group:           Group.
    :type group:            string

    :param force:           No error if existing, make parent directories
                            as needed.
    :type force:            boolean

    :raises:                :class:`UnprocessableEntity` if dir_path not given.
    """

    if dir_path:
        _create_directory(dir_path, force, **kwargs)
        if user or group:
            chown(dir_path, user, group, **kwargs)
    else:
        raise exception.UnprocessableEntity(
            _("Cannot create a blank directory."))


def chown(path, user, group, recursive=True, force=False, **kwargs):
    """Changes the owner and group of a given file.

    seealso:: _execute_shell_cmd for valid optional keyword arguments.

    :param path:         Path to the modified file.
    :type path:          string

    :param user:         Owner.
    :type user:          string

    :param group:        Group.
    :type group:         string

    :param recursive:    Operate on files and directories recursively.
    :type recursive:     boolean

    :param force:        Suppress most error messages.
    :type force:         boolean

    :raises:             :class:`UnprocessableEntity` if path not given.
    :raises:             :class:`UnprocessableEntity` if owner/group not given.
    """

    if not path:
        raise exception.UnprocessableEntity(
            _("Cannot change ownership of a blank file or directory."))
    if not user and not group:
        raise exception.UnprocessableEntity(
            _("Please specify owner or group, or both."))

    owner_group_modifier = _build_user_group_pair(user, group)
    options = (('f', force), ('R', recursive))
    _execute_shell_cmd('chown', options, owner_group_modifier, path, **kwargs)


def _build_user_group_pair(user, group):
    return "%s:%s" % tuple((v if v else '') for v in (user, group))


def _create_directory(dir_path, force=True, **kwargs):
    """Create a given directory.

    :param dir_path:        Path to the created directory.
    :type dir_path:         string

    :param force:           No error if existing, make parent directories
                            as needed.
    :type force:            boolean
    :param as_root: Run as root user, default: False.
    """

    options = (('p', force),)
    _execute_shell_cmd('mkdir', options, dir_path, **kwargs)


def chmod(path, mode, recursive=True, force=False, **kwargs):
    """Changes the mode of a given file.

    :seealso: Modes for more information on the representation of modes.
    :seealso: _execute_shell_cmd for valid optional keyword arguments.

    :param path:            Path to the modified file.
    :type path:             string

    :param mode:            File permissions (modes).
                            The modes will be applied in the following order:
                            reset (=), add (+), remove (-)
    :type mode:             FileMode

    :param recursive:       Operate on files and directories recursively.
    :type recursive:        boolean

    :param force:           Suppress most error messages.
    :type force:            boolean

    :raises:                :class:`UnprocessableEntity` if path not given.
    :raises:                :class:`UnprocessableEntity` if no mode given.
    """

    if path:
        options = (('f', force), ('R', recursive))
        shell_modes = _build_shell_chmod_mode(mode)
        _execute_shell_cmd('chmod', options, shell_modes, path, **kwargs)
    else:
        raise exception.UnprocessableEntity(
            _("Cannot change mode of a blank file."))


def change_user_group(user, group, append=True, add_group=True, **kwargs):
    """Adds a user to groups by using the usermod linux command with -a and
    -G options.

    seealso:: _execute_shell_cmd for valid optional keyword arguments.

    :param user:            Username.
    :type user:             string

    :param group:           Group names.
    :type group:            comma separated string

    :param  append:         Adds user to a group.
    :type append:           boolean

    :param add_group:       Lists the groups that the user is a member of.
                            While adding a new groups to an existing user
                            with '-G' option alone, will remove all existing
                            groups that user belongs. Therefore, always add
                            the '-a' (append) with '-G' option to add or
                            append new groups.
    :type add_group:        boolean

    :raises:                :class:`UnprocessableEntity` if user or group not
                            given.
    """

    if not user:
        raise exception.UnprocessableEntity(_("Missing user."))
    elif not group:
        raise exception.UnprocessableEntity(_("Missing group."))

    options = (('a', append), ('G', add_group))
    _execute_shell_cmd('usermod', options, group, user, **kwargs)


def _build_shell_chmod_mode(mode):
    """
    Build a shell representation of given mode.

    :seealso: Modes for more information on the representation of modes.

    :param mode:            File permissions (modes).
    :type mode:             FileModes

    :raises:                :class:`UnprocessableEntity` if no mode given.

    :returns: Following string for any non-empty modes:
              '=<reset mode>,+<add mode>,-<remove mode>'
    """

    # Handle methods passed in as constant fields.
    if inspect.ismethod(mode):
        mode = mode()

    if mode and mode.has_any():
        text_modes = (('=', mode.get_reset_mode()),
                      ('+', mode.get_add_mode()),
                      ('-', mode.get_remove_mode()))
        return ','.join(
            ['{0:s}{1:03o}'.format(item[0], item[1]) for item in text_modes
             if item[1]])
    else:
        raise exception.UnprocessableEntity(_("No file mode specified."))


def remove(path, force=False, recursive=True, **kwargs):
    """Remove a given file or directory.

    :seealso: _execute_shell_cmd for valid optional keyword arguments.

    :param path:            Path to the removed file.
    :type path:             string

    :param force:           Ignore nonexistent files.
    :type force:            boolean

    :param recursive:       Remove directories and their contents recursively.
    :type recursive:        boolean

    :raises:                :class:`UnprocessableEntity` if path not given.
    """

    if path:
        options = (('f', force), ('R', recursive))
        _execute_shell_cmd('rm', options, path, **kwargs)
    else:
        raise exception.UnprocessableEntity(_("Cannot remove a blank file."))


def move(source, destination, force=False, **kwargs):
    """Move a given file or directory to a new location.
    Move attempts to preserve the original ownership, permissions and
    timestamps.

    :seealso: _execute_shell_cmd for valid optional keyword arguments.

    :param source:          Path to the source location.
    :type source:           string

    :param destination:     Path to the destination location.
    :type destination:      string

    :param force:           Do not prompt before overwriting.
    :type force:            boolean

    :raises:                :class:`UnprocessableEntity` if source or
                            destination not given.
    """

    if not source:
        raise exception.UnprocessableEntity(_("Missing source path."))
    elif not destination:
        raise exception.UnprocessableEntity(_("Missing destination path."))

    options = (('f', force),)
    _execute_shell_cmd('mv', options, source, destination, **kwargs)


def copy(source, destination, force=False, preserve=False, recursive=True,
         dereference=False, **kwargs):
    """Copy a given file or directory to another location.
    Copy does NOT attempt to preserve ownership, permissions and timestamps
    unless the 'preserve' option is enabled.

    :seealso: _execute_shell_cmd for valid optional keyword arguments.

    :param source:          Path to the source location.
    :type source:           string

    :param destination:     Path to the destination location.
    :type destination:      string

    :param force:           If an existing destination file cannot be
                            opened, remove it and try again.
    :type force:            boolean

    :param preserve:        Preserve mode, ownership and timestamps.
    :type preserve:         boolean

    :param recursive:       Copy directories recursively.
    :type recursive:        boolean

    :param dereference:     Follow symbolic links when copying from them.
    :type dereference:      boolean

    :raises:                :class:`UnprocessableEntity` if source or
                            destination not given.
    """

    if not source:
        raise exception.UnprocessableEntity(_("Missing source path."))
    elif not destination:
        raise exception.UnprocessableEntity(_("Missing destination path."))

    options = (('f', force), ('p', preserve), ('R', recursive),
               ('L', dereference))
    _execute_shell_cmd('cp', options, source, destination, **kwargs)


def get_bytes_free_on_fs(path):
    """
    Returns the number of bytes free for the filesystem that path is on
    """
    v = os.statvfs(path)
    return v.f_bsize * v.f_bavail


def list_files_in_directory(root_dir, recursive=False, pattern=None,
                            include_dirs=False, as_root=False):
    """
    Return absolute paths to all files in a given root directory.

    :param root_dir            Path to the root directory.
    :type root_dir             string

    :param recursive           Also descend into sub-directories if True.
    :type recursive            boolean

    :param pattern             Return only names matching the pattern.
    :type pattern              string

    :param include_dirs        Include paths to individual sub-directories.
    :type include_dirs         boolean
    """
    if as_root:
        cmd_args = [root_dir, '-noleaf']
        if not recursive:
            cmd_args.extend(['-maxdepth', '0'])
        if not include_dirs:
            cmd_args.extend(['-type', 'f'])
        if pattern:
            cmd_args.extend(['-regextype', 'posix-extended',
                             '-regex', os.path.join('.*', pattern) + '$'])
        files = _execute_shell_cmd('find', [], *cmd_args, as_root=True)
        return {fp for fp in files.splitlines()}

    return {os.path.abspath(os.path.join(root, name))
            for (root, dirs, files) in os.walk(root_dir, topdown=True)
            if recursive or (root == root_dir)
            for name in (files + (dirs if include_dirs else []))
            if not pattern or re.match(pattern, name)}


def _build_command_options(options):
    """Build a list of flags from given pairs (option, is_enabled).
    Each option is prefixed with a single '-'.
    Include only options for which is_enabled=True.
    """

    return ['-' + item[0] for item in options if item[1]]


def get_device(path, as_root=False):
    """Get the device that a given path exists on."""
    stdout = _execute_shell_cmd('df', [], path, as_root=as_root)
    return stdout.splitlines()[1].split()[0]


def is_mount(path):
    """Check if the given directory path is a mountpoint. Try the standard
    ismount first. This fails if the path is not accessible though, so resort
    to checking as the root user (which is slower).
    """
    if os.access(path, os.R_OK):
        return os.path.ismount(path)
    if not exists(path, is_directory=True, as_root=True):
        return False
    directory_dev = get_device(path, as_root=True)
    parent_dev = get_device(os.path.join(path, '..'), as_root=True)
    return directory_dev != parent_dev


def get_current_user():
    """Returns name of the current OS user"""
    return pwd.getpwuid(os.getuid())[0]


def create_user(user_name, user_id, group_name=None, group_id=None):
    group_name = group_name or user_name
    group_id = group_id or user_id

    try:
        _execute_shell_cmd('groupadd', [], '--gid', group_id, group_name,
                           as_root=True)
    except exception.ProcessExecutionError as err:
        if 'already exists' not in err.stderr:
            raise exception.UnprocessableEntity(
                'Failed to add group %s, error: %s' % (group_name, err.stderr)
            )

    try:
        _execute_shell_cmd('useradd', [], '--uid', user_id, '--gid', group_id,
                           '-M', user_name, as_root=True)
    except exception.ProcessExecutionError as err:
        if 'already exists' not in err.stderr:
            raise exception.UnprocessableEntity(
                'Failed to add user %s, error: %s' % (user_name, err.stderr)
            )


def remove_dir_contents(folder):
    """Remove all the files and sub-directories but keep the folder.

    Use shell=True here because shell=False doesn't support '*'
    """
    path = os.path.join(folder, '*')
    _execute_shell_cmd(f'rm -rf {path}', [], shell=True, as_root=True)
