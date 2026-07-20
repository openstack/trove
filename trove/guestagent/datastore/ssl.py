# Copyright 2026 PS Cloud Services
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

import abc
import json
import os
import tempfile

from oslo_log import log as logging
from trove.common import cfg
from trove.common import exception
from trove.common import ssl
from trove.common.ssl import TroveSSL
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class SSLManager(object):
    def _get_ssl_state_file(self):
        return os.path.join(
            CONF.injected_config_location,
            "ssl_state.json")

    def _write_ssl_state(self, state):
        state_file = self._get_ssl_state_file()
        with tempfile.NamedTemporaryFile(
                mode="w",
                dir=os.path.dirname(state_file),
                delete=False) as fp:
            json.dump(state, fp)
            fp.flush()
            os.fsync(fp.fileno())
            tmp_name = fp.name

        os.replace(tmp_name, state_file)

    def _read_ssl_state(self):
        with open(self._get_ssl_state_file()) as fp:
            return json.load(fp)

    def _delete_ssl_state(self):
        state_file = self._get_ssl_state_file()
        if os.path.exists(state_file):
            os.unlink(state_file)

    def _write_ssl_files(self, cert_container):
        for key, filename in self._get_ssl_files().items():
            payload = cert_container.get(key)
            if not payload:
                continue
            operating_system.write_file(
                filename,
                payload,
                as_root=True)
            operating_system.chown(
                filename,
                user=self.app.database_service_uid,
                group=self.app.database_service_gid,
                force=True,
                as_root=True)
            operating_system.chmod(
                filename,
                FileMode.SET_USR_RW(),
                as_root=True)
            operating_system.sync(os.path.dirname(filename))

    def _read_ssl_files(self):
        files = {}

        for key, filename in self._get_ssl_files().items():
            files[key] = operating_system.read_file(
                filename,
                as_root=True)

        return files

    def _save_ssl_state(self):
        status = self.show_ssl_status()
        state = {
            "status": status["status"],
            "mode": CONF.ssl_mode,
        }
        if status["status"] == "on":
            state["files"] = self._read_ssl_files()

        self._write_ssl_state(state)

    def ssl_mode_at_least(self, current_mode, required_mode):
        priorities = [
            ssl.MODE_BASIC, ssl.MODE_ENFORCED, ssl.MODE_MTLS]
        try:
            return (
                priorities.index(current_mode) >=
                priorities.index(required_mode)
            )
        except ValueError:
            return False

    def ssl_show(self, context):
        LOG.info("Getting ssl status for instance")
        result = self.show_ssl_status()
        if result["status"] == "on":
            result["mode"] = CONF.ssl_mode
            ssl = TroveSSL(context)
            cert_details = ssl.certificate_details(result["certificate"])
            cert_details["payload"] = result["certificate"]
            del result["certificate"]
            return {**result, "certificate": cert_details}
        else:
            return result

    def ssl_action(self, context, mode, container, enable, disable):
        if enable and disable:
            raise exception.BadRequest("Cannot enable and disable ssl")
        LOG.info(
            "SSL action for instance: mode=%s, enable=%s, disable=%s",
            mode, enable, disable)
        result = {}
        if enable:
            result["restart_required"] = self.enable_ssl_certificate(
                mode, container)
        elif disable:
            result["restart_required"] = self.disable_ssl_certificate()
        return result

    def ssl_rollback(self, context):
        state = self._read_ssl_state()
        LOG.info("Rolling back ssl configuration for instance")
        LOG.debug("Previous ssl status: %s, mode: %s",
                  state['status'], state['mode'])
        result = {
            "status": state["status"]
        }
        if state["status"] == "off":
            result["restart_required"] = self._disable_ssl_certificate_impl()
            self.override_guest_info(ssl_mode=None)
            result["mode"] = None
        else:
            self._write_ssl_files(state["files"])
            result["restart_required"] = self._enable_ssl_certificate_impl(
                state["mode"])
            self.override_guest_info(ssl_mode=state["mode"])
            result["mode"] = state["mode"]

        self._delete_ssl_state()
        return result

    def enable_ssl_certificate(
            self, mode, cert_container, apply_overrides=True,
            is_startup=False):
        LOG.debug("Called enable_ssl_certificate, mode=%s", mode)
        if not is_startup:
            self._save_ssl_state()
        self._write_ssl_files(cert_container)
        restart_required = self._enable_ssl_certificate_impl(
            mode, apply_overrides=apply_overrides)
        self.override_guest_info(ssl_mode=mode)
        return restart_required

    def disable_ssl_certificate(self):
        LOG.debug("Called disable_ssl_certificate")
        self._save_ssl_state()
        restart_required = self._disable_ssl_certificate_impl()
        self.override_guest_info(ssl_mode=None)
        return restart_required

    def _enable_ssl_certificate_impl(self, mode, apply_overrides=True):
        raise exception.TroveError("ssl enable not implemented")

    def _disable_ssl_certificate_impl(self, apply_overrides=True):
        raise exception.TroveError("ssl disable not implemented")

    def show_ssl_status(self):
        """Manager should return current ssl certificate details and current
        ssl status (on/off)
        """
        return {"status": "not implemented"}

    @abc.abstractmethod
    def _get_ssl_files(self):
        """Manager should return dict with private_key, certificate and ca
        as keys and corresponding paths as values.
        """
        return {}
