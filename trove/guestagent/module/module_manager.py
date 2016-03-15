# Copyright 2016 Tesora, Inc.
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

import datetime
import os

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import stream_codecs
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ModuleManager():
    """This is a Manager utility class (mixin) for managing module-related
    tasks.
    """

    MODULE_APPLY_TO_ALL = 'all'
    MODULE_BASE_DIR = guestagent_utils.build_file_path('~', 'modules')
    MODULE_CONTENTS_FILENAME = 'contents.dat'
    MODULE_RESULT_FILENAME = 'result.json'

    @classmethod
    def get_current_timestamp(cls):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def apply_module(cls, driver, module_type, name, tenant,
                     datastore, ds_version, contents, module_id, md5,
                     auto_apply, visible):
        tenant = tenant or cls.MODULE_APPLY_TO_ALL
        datastore = datastore or cls.MODULE_APPLY_TO_ALL
        ds_version = ds_version or cls.MODULE_APPLY_TO_ALL
        module_dir = cls.build_module_dir(module_type, module_id)
        data_file = cls.write_module_contents(module_dir, contents, md5)
        applied = True
        message = None
        now = cls.get_current_timestamp()
        default_result = cls.build_default_result(
            module_type, name, tenant, datastore,
            ds_version, module_id, md5, auto_apply, visible, now)
        result = cls.read_module_result(module_dir, default_result)
        try:
            applied, message = driver.apply(
                name, datastore, ds_version, data_file)
        except Exception as ex:
            LOG.exception(_("Could not apply module '%s'") % name)
            applied = False
            message = ex.message
        finally:
            status = 'OK' if applied else 'ERROR'
            admin_only = (not visible or tenant == cls.MODULE_APPLY_TO_ALL or
                          auto_apply)
            result['status'] = status
            result['message'] = message
            result['updated'] = now
            result['id'] = module_id
            result['md5'] = md5
            result['tenant'] = tenant
            result['auto_apply'] = auto_apply
            result['visible'] = visible
            result['admin_only'] = admin_only
            cls.write_module_result(module_dir, result)
        return result

    @classmethod
    def build_module_dir(cls, module_type, module_id):
        sub_dir = os.path.join(module_type, module_id)
        module_dir = guestagent_utils.build_file_path(
            cls.MODULE_BASE_DIR, sub_dir)
        if not operating_system.exists(module_dir, is_directory=True):
            operating_system.create_directory(module_dir, force=True)
        return module_dir

    @classmethod
    def write_module_contents(cls, module_dir, contents, md5):
        contents_file = cls.build_contents_filename(module_dir)
        operating_system.write_file(contents_file, contents,
                                    codec=stream_codecs.Base64Codec(),
                                    encode=False)
        return contents_file

    @classmethod
    def build_contents_filename(cls, module_dir):
        contents_file = guestagent_utils.build_file_path(
            module_dir, cls.MODULE_CONTENTS_FILENAME)
        return contents_file

    @classmethod
    def build_default_result(cls, module_type, name, tenant,
                             datastore, ds_version, module_id, md5,
                             auto_apply, visible, now):
        admin_only = (not visible or tenant == cls.MODULE_APPLY_TO_ALL or
                      auto_apply)
        result = {
            'type': module_type,
            'name': name,
            'datastore': datastore,
            'datastore_version': ds_version,
            'tenant': tenant,
            'id': module_id,
            'md5': md5,
            'status': None,
            'message': None,
            'created': now,
            'updated': now,
            'removed': None,
            'auto_apply': auto_apply,
            'visible': visible,
            'admin_only': admin_only,
            'contents': None,
        }
        return result

    @classmethod
    def read_module_result(cls, result_file, default=None):
        result_file = cls.get_result_filename(result_file)
        result = default
        try:
            result = operating_system.read_file(
                result_file, codec=stream_codecs.JsonCodec())
        except Exception:
            if not result:
                LOG.exception(_("Could not find module result in %s") %
                              result_file)
                raise
        return result

    @classmethod
    def get_result_filename(cls, file_or_dir):
        result_file = file_or_dir
        if operating_system.exists(file_or_dir, is_directory=True):
            result_file = guestagent_utils.build_file_path(
                file_or_dir, cls.MODULE_RESULT_FILENAME)
        return result_file

    @classmethod
    def write_module_result(cls, result_file, result):
        result_file = cls.get_result_filename(result_file)
        operating_system.write_file(
            result_file, result, codec=stream_codecs.JsonCodec())

    @classmethod
    def read_module_results(cls, is_admin=False, include_contents=False):
        """Read all the module results on the guest and return a list
        of them.
        """
        results = []
        pattern = cls.MODULE_RESULT_FILENAME
        result_files = operating_system.list_files_in_directory(
            cls.MODULE_BASE_DIR, recursive=True, pattern=pattern)
        for result_file in result_files:
            result = cls.read_module_result(result_file)
            if (not result.get('removed') and
                    (is_admin or result.get('visible'))):
                if include_contents:
                    codec = stream_codecs.Base64Codec()
                    if not is_admin and result.get('admin_only'):
                        contents = (
                            "Must be admin to retrieve contents for module %s"
                            % result.get('name', 'Unknown'))
                        result['contents'] = codec.serialize(contents)
                    else:
                        contents_dir = os.path.dirname(result_file)
                        contents_file = cls.build_contents_filename(
                            contents_dir)
                        result['contents'] = operating_system.read_file(
                            contents_file, codec=codec, decode=False)
                results.append(result)
        return results

    @classmethod
    def remove_module(cls, driver, module_type, module_id, name,
                      datastore, ds_version):
        datastore = datastore or cls.MODULE_APPLY_TO_ALL
        ds_version = ds_version or cls.MODULE_APPLY_TO_ALL
        module_dir = cls.build_module_dir(module_type, module_id)
        contents_file = cls.build_contents_filename(module_dir)

        if not operating_system.exists(cls.get_result_filename(module_dir)):
            raise exception.NotFound(
                _("Module '%s' has not been applied") % name)
        try:
            removed, message = driver.remove(
                name, datastore, ds_version, contents_file)
            cls.remove_module_result(module_dir)
        except Exception:
            LOG.exception(_("Could not remove module '%s'") % name)
            raise
        return removed, message

    @classmethod
    def remove_module_result(cls, result_file):
        now = cls.get_current_timestamp()
        result = cls.read_module_result(result_file, None)
        result['removed'] = now
        cls.write_module_result(result_file, result)
