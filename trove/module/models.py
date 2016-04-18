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

"""Model classes that form the core of Module functionality."""

from datetime import datetime
import hashlib
import six
from sqlalchemy.sql.expression import or_

from oslo_log import log as logging

from trove.common import cfg
from trove.common import crypto_utils
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.datastore import models as datastore_models
from trove.db import models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Modules(object):

    DEFAULT_LIMIT = CONF.modules_page_size
    ENCRYPT_KEY = CONF.module_aes_cbc_key
    VALID_MODULE_TYPES = [mt.lower() for mt in CONF.module_types]
    MATCH_ALL_NAME = 'all'

    @staticmethod
    def load(context, datastore=None):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        query_opts = {'deleted': False}
        if datastore:
            if datastore.lower() == Modules.MATCH_ALL_NAME:
                datastore = None
            query_opts['datastore_id'] = datastore
        if context.is_admin:
            db_info = DBModule.find_all(**query_opts)
            if db_info.count() == 0:
                LOG.debug("No modules found for admin user")
        else:
            # build a query manually, since we need current tenant
            # plus the 'all' tenant ones
            query_opts['visible'] = True
            db_info = DBModule.query().filter_by(**query_opts)
            db_info = db_info.filter(or_(DBModule.tenant_id == context.tenant,
                                         DBModule.tenant_id.is_(None)))
            if db_info.count() == 0:
                LOG.debug("No modules found for tenant %s" % context.tenant)
        modules = db_info.all()
        return modules

    @staticmethod
    def load_auto_apply(context, datastore_id, datastore_version_id):
        """Return all the auto-apply modules for the given criteria."""
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        query_opts = {'deleted': False,
                      'auto_apply': True}
        db_info = DBModule.query().filter_by(**query_opts)
        db_info = Modules.add_tenant_filter(db_info, context.tenant)
        db_info = Modules.add_datastore_filter(db_info, datastore_id)
        db_info = Modules.add_ds_version_filter(db_info, datastore_version_id)
        if db_info.count() == 0:
            LOG.debug("No auto-apply modules found for tenant %s" %
                      context.tenant)
        modules = db_info.all()
        return modules

    @staticmethod
    def add_tenant_filter(query, tenant_id):
        return query.filter(or_(DBModule.tenant_id == tenant_id,
                                DBModule.tenant_id.is_(None)))

    @staticmethod
    def add_datastore_filter(query, datastore_id):
        return query.filter(or_(DBModule.datastore_id == datastore_id,
                                DBModule.datastore_id.is_(None)))

    @staticmethod
    def add_ds_version_filter(query, datastore_version_id):
        return query.filter(or_(
            DBModule.datastore_version_id == datastore_version_id,
            DBModule.datastore_version_id.is_(None)))

    @staticmethod
    def load_by_ids(context, module_ids):
        """Return all the modules for the given ids. Screens out the ones
        for other tenants, unless the user is admin.
        """
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        modules = []
        if module_ids:
            query_opts = {'deleted': False}
            db_info = DBModule.query().filter_by(**query_opts)
            if not context.is_admin:
                db_info = Modules.add_tenant_filter(db_info, context.tenant)
            db_info = db_info.filter(DBModule.id.in_(module_ids))
            modules = db_info.all()
        return modules


class Module(object):

    def __init__(self, context, module_id):
        self.context = context
        self.module_id = module_id

    @staticmethod
    def create(context, name, module_type, contents,
               description, tenant_id, datastore,
               datastore_version, auto_apply, visible, live_update,
               priority_apply, apply_order, full_access):
        if module_type.lower() not in Modules.VALID_MODULE_TYPES:
            LOG.error(_("Valid module types: %s") % Modules.VALID_MODULE_TYPES)
            raise exception.ModuleTypeNotFound(module_type=module_type)
        Module.validate_action(
            context, 'create', tenant_id, auto_apply, visible, priority_apply,
            full_access)
        datastore_id, datastore_version_id = Module.validate_datastore(
            datastore, datastore_version)
        if Module.key_exists(
                name, module_type, tenant_id,
                datastore_id, datastore_version_id):
            datastore_str = datastore_id or Modules.MATCH_ALL_NAME
            ds_version_str = datastore_version_id or Modules.MATCH_ALL_NAME
            raise exception.ModuleAlreadyExists(
                name=name, datastore=datastore_str, ds_version=ds_version_str)
        md5, processed_contents = Module.process_contents(contents)
        is_admin = context.is_admin
        if full_access:
            is_admin = 0
        module = DBModule.create(
            name=name,
            type=module_type.lower(),
            contents=processed_contents,
            description=description,
            tenant_id=tenant_id,
            datastore_id=datastore_id,
            datastore_version_id=datastore_version_id,
            auto_apply=auto_apply,
            visible=visible,
            live_update=live_update,
            priority_apply=priority_apply,
            apply_order=apply_order,
            is_admin=is_admin,
            md5=md5)
        return module

    # Certain fields require admin access to create/change/delete
    @staticmethod
    def validate_action(context, action_str, tenant_id, auto_apply, visible,
                        priority_apply, full_access):
        admin_options_str = None
        option_strs = []
        if tenant_id is None:
            option_strs.append(_("Tenant: %s") % Modules.MATCH_ALL_NAME)
        if auto_apply:
            option_strs.append(_("Auto: %s") % auto_apply)
        if not visible:
            option_strs.append(_("Visible: %s") % visible)
        if priority_apply:
            option_strs.append(_("Priority: %s") % priority_apply)
        if full_access is not None:
            if full_access and option_strs:
                admin_options_str = "(" + ", ".join(option_strs) + ")"
                raise exception.InvalidModelError(
                    errors=_('Cannot make module full access: %s') %
                    admin_options_str)
            option_strs.append(_("Full Access: %s") % full_access)
        if option_strs:
            admin_options_str = "(" + ", ".join(option_strs) + ")"
        if not context.is_admin and admin_options_str:
            raise exception.ModuleAccessForbidden(
                action=action_str, options=admin_options_str)
        return admin_options_str

    @staticmethod
    def validate_datastore(datastore, datastore_version):
        datastore_id = None
        datastore_version_id = None
        if datastore:
            if datastore_version:
                ds, ds_ver = datastore_models.get_datastore_version(
                    type=datastore, version=datastore_version)
                datastore_id = ds.id
                datastore_version_id = ds_ver.id
            else:
                ds = datastore_models.Datastore.load(datastore)
                datastore_id = ds.id
        elif datastore_version:
            msg = _("Cannot specify version without datastore")
            raise exception.BadRequest(message=msg)
        return datastore_id, datastore_version_id

    @staticmethod
    def key_exists(name, module_type, tenant_id, datastore_id,
                   datastore_version_id):
        try:
            DBModule.find_by(
                name=name, type=module_type, tenant_id=tenant_id,
                datastore_id=datastore_id,
                datastore_version_id=datastore_version_id,
                deleted=False)
            return True
        except exception.ModelNotFoundError:
            return False

    # We encrypt the contents (which should be encoded already, since it
    # might be in binary format) and then encode them again so they can
    # be stored in a text field in the Trove database.
    @staticmethod
    def process_contents(contents):
        md5 = contents
        if isinstance(md5, six.text_type):
            md5 = md5.encode('utf-8')
        md5 = hashlib.md5(md5).hexdigest()
        encrypted_contents = crypto_utils.encrypt_data(
            contents, Modules.ENCRYPT_KEY)
        return md5, crypto_utils.encode_data(encrypted_contents)

    # Do the reverse to 'deprocess' the contents
    @staticmethod
    def deprocess_contents(processed_contents):
        encrypted_contents = crypto_utils.decode_data(processed_contents)
        return crypto_utils.decrypt_data(
            encrypted_contents, Modules.ENCRYPT_KEY)

    @staticmethod
    def delete(context, module):
        Module.validate_action(
            context, 'delete',
            module.tenant_id, module.auto_apply, module.visible,
            module.priority_apply, None)
        Module.enforce_live_update(module.id, module.live_update, module.md5)
        module.deleted = True
        module.deleted_at = datetime.utcnow()
        module.save()

    @staticmethod
    def enforce_live_update(module_id, live_update, md5):
        if not live_update:
            instances = DBInstanceModule.find_all(
                module_id=module_id, md5=md5, deleted=False).all()
            if instances:
                raise exception.ModuleAppliedToInstance()

    @staticmethod
    def load(context, module_id):
        module = None
        try:
            if context.is_admin:
                module = DBModule.find_by(id=module_id, deleted=False)
            else:
                module = DBModule.find_by(
                    id=module_id, tenant_id=context.tenant, visible=True,
                    deleted=False)
        except exception.ModelNotFoundError:
            # See if we have the module in the 'all' tenant section
            if not context.is_admin:
                try:
                    module = DBModule.find_by(
                        id=module_id, tenant_id=None, visible=True,
                        deleted=False)
                except exception.ModelNotFoundError:
                    pass  # fall through to the raise below

        if not module:
            msg = _("Module with ID %s could not be found.") % module_id
            raise exception.ModelNotFoundError(msg)

        # Save the encrypted contents in case we need to put it back
        # when updating the record
        module.encrypted_contents = module.contents
        module.contents = Module.deprocess_contents(module.contents)
        return module

    @staticmethod
    def update(context, module, original_module, full_access):
        Module.enforce_live_update(
            original_module.id, original_module.live_update,
            original_module.md5)
        # we don't allow any changes to 'is_admin' modules by non-admin
        if original_module.is_admin and not context.is_admin:
            raise exception.ModuleAccessForbidden(
                action='update', options='(Module is an admin module)')
        # we don't allow any changes to admin-only attributes by non-admin
        admin_options = Module.validate_action(
            context, 'update', module.tenant_id, module.auto_apply,
            module.visible, module.priority_apply, full_access)
        # make sure we set the is_admin flag, but only if it was
        # originally is_admin or we changed an admin option
        module.is_admin = original_module.is_admin or (
            1 if admin_options else 0)
        # but we turn it on/off if full_access is specified
        if full_access is not None:
            module.is_admin = 0 if full_access else 1
        ds_id, ds_ver_id = Module.validate_datastore(
            module.datastore_id, module.datastore_version_id)
        if module.contents != original_module.contents:
            md5, processed_contents = Module.process_contents(module.contents)
            module.md5 = md5
            module.contents = processed_contents
        elif hasattr(original_module, 'encrypted_contents'):
            # on load the contents may have been decrypted, so
            # we need to put the encrypted contents back before we update
            module.contents = original_module.encrypted_contents
        if module.datastore_id:
            module.datastore_id = ds_id
        if module.datastore_version_id:
            module.datastore_version_id = ds_ver_id

        module.updated = datetime.utcnow()
        DBModule.save(module)


class InstanceModules(object):

    @staticmethod
    def load(context, instance_id=None, module_id=None, md5=None):
        db_info = InstanceModules.load_all(
            context, instance_id=instance_id, module_id=module_id, md5=md5)
        if db_info.count() == 0:
            LOG.debug("No instance module records found")

        limit = utils.pagination_limit(
            context.limit, Modules.DEFAULT_LIMIT)
        data_view = DBInstanceModule.find_by_pagination(
            'modules', db_info, 'foo', limit=limit, marker=context.marker)
        next_marker = data_view.next_page_marker
        return data_view.collection, next_marker

    @staticmethod
    def load_all(context, instance_id=None, module_id=None, md5=None):
        query_opts = {'deleted': False}
        if instance_id:
            query_opts['instance_id'] = instance_id
        if module_id:
            query_opts['module_id'] = module_id
        if md5:
            query_opts['md5'] = md5
        return DBInstanceModule.find_all(**query_opts)


class InstanceModule(object):

    def __init__(self, context, instance_id, module_id):
        self.context = context
        self.instance_id = instance_id
        self.module_id = module_id

    @staticmethod
    def create(context, instance_id, module_id, md5):
        instance_module = None
        # First mark any 'old' records as deleted and/or update the
        # current one.
        old_ims = InstanceModules.load_all(
            context, instance_id=instance_id, module_id=module_id)
        for old_im in old_ims:
            if old_im.md5 == md5 and not instance_module:
                instance_module = old_im
                InstanceModule.update(context, instance_module)
            else:
                if old_im.md5 == md5 and instance_module:
                    LOG.debug("Found dupe IM record %s; marking as deleted "
                              "(instance %s, module %s)." %
                              (old_im.id, instance_id, module_id))
                else:
                    LOG.debug("Deleting IM record %s (instance %s, "
                              "module %s)." %
                              (old_im.id, instance_id, module_id))
                InstanceModule.delete(context, old_im)

        # If we don't have an instance module, it means we need to create
        # a new one.
        if not instance_module:
            instance_module = DBInstanceModule.create(
                instance_id=instance_id,
                module_id=module_id,
                md5=md5)
        return instance_module

    @staticmethod
    def delete(context, instance_module):
        instance_module.deleted = True
        instance_module.deleted_at = datetime.utcnow()
        instance_module.save()

    @staticmethod
    def load(context, instance_id, module_id, deleted=False):
        instance_module = None
        try:
            instance_module = DBInstanceModule.find_by(
                instance_id=instance_id, module_id=module_id, deleted=deleted)
        except exception.ModelNotFoundError:
            pass

        return instance_module

    @staticmethod
    def update(context, instance_module):
        instance_module.updated = datetime.utcnow()
        DBInstanceModule.save(instance_module)


class DBInstanceModule(models.DatabaseModelBase):
    _data_fields = [
        'id', 'instance_id', 'module_id', 'md5', 'created',
        'updated', 'deleted', 'deleted_at']


class DBModule(models.DatabaseModelBase):
    _data_fields = [
        'id', 'name', 'type', 'contents', 'description',
        'tenant_id', 'datastore_id', 'datastore_version_id',
        'auto_apply', 'visible', 'live_update',
        'priority_apply', 'apply_order', 'is_admin',
        'md5', 'created', 'updated', 'deleted', 'deleted_at']


def persisted_models():
    return {'modules': DBModule, 'instance_modules': DBInstanceModule}
