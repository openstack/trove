# Copyright 2026 PS Cloud Services
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

from barbicanclient import exceptions as barbican_exceptions
from cryptography.hazmat.primitives.serialization \
    import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from datetime import datetime
import OpenSSL.crypto as crypto
from oslo_log import log as logging
from trove.common import cfg
from trove.common.clients import barbican_client

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

MODE_BUILTIN = 'builtin'
MODE_BASIC = 'basic'
MODE_ENFORCED = 'enforced'
MODE_MTLS = 'mtls'


class TroveSSL(object):
    def __init__(self, context):
        self._context = context

    # Fetch certificate, key and ca from p12 container
    def get_p12_bundle(self, p12_ref, password_ref=None):
        barbican = barbican_client(self._context)
        pkcs12_secret = barbican.secrets.get(p12_ref)

        p12_pass = None
        if password_ref:
            p12_pass = barbican.secrets.get(password_ref).payload
            if isinstance(p12_pass, str):
                p12_pass = p12_pass.encode("utf-8")

        pk, cert, ca_chain = pkcs12.load_key_and_certificates(
            pkcs12_secret.payload,
            p12_pass,
            backend=default_backend()
        )

        pk = pk.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption()
        ).decode("utf-8")

        cert = cert.public_bytes(Encoding.PEM).decode("utf-8")

        ca_pems = ""
        if ca_chain:
            for ca in ca_chain:
                ca_pems += ca.public_bytes(
                    Encoding.PEM).decode("utf-8")

        return {
            'private_key': pk,
            'certificate': cert,
            'ca': ca_pems}

    def certificate_details(self, cert_payload):
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_payload)

        subject = cert.get_subject()
        expiry_bytes = cert.get_notAfter()
        expiry_str = expiry_bytes.decode("ascii")
        expiry = datetime.strptime(expiry_str, "%Y%m%d%H%M%SZ")

        # Extract SANs
        san_list = []
        # Loop through all extensions in the certificate
        for i in range(cert.get_extension_count()):
            ext = cert.get_extension(i)
            # Check if the extension is 'subjectAltName'
            if ext.get_short_name() == b"subjectAltName":
                san_str = str(ext)
                san_list = [item.strip() for item in san_str.split(",")]

        return {
            'cn': subject.CN,
            'expire_at': expiry,
            'san': san_list if san_list else None
        }

    def register_consumer(self, uri, resource_type, resource_id):
        barbican = barbican_client(self._context)
        barbican.secrets.register_consumer(
            uri, 'database', resource_type, resource_id)

    def remove_consumer(self, uri, resource_type, resource_id):
        barbican = barbican_client(self._context)
        barbican.secrets.remove_consumer(
            uri, 'database', resource_type, resource_id)

    def disable_instance_ssl(self, instance):
        rollback_changes = []
        if instance.db_info.ssl_ref:
            try:
                args = [instance.db_info.ssl_ref, 'instance', instance.id]
                self.remove_consumer(*args)
                rollback_changes.append({'type': 'register', 'args': args})
            except barbican_exceptions.HTTPClientError as e:
                LOG.info('Unable to remove consumer for %s: %s',
                         instance.db_info.ssl_ref, e)
            instance.db_info.ssl_ref = None
        instance.db_info.ssl_mode = None
        instance.db_info.save()
        return rollback_changes

    def enable_instance_ssl(self, instance, mode, container_ref):
        rollback_changes = []
        if instance.db_info.ssl_ref and \
           instance.db_info.ssl_ref != container_ref:
            LOG.info("Instance %s already has container ref, tidying up %s",
                     instance.id, instance.db_info.ssl_ref)
            # Certificate refresh, remove consumer from previous ref
            rollback_changes.extend(self.disable_instance_ssl(instance))

        instance.db_info.ssl_mode = mode
        if container_ref:
            instance.db_info.ssl_ref = container_ref
            try:
                args = container_ref, 'instance', instance.id
                self.register_consumer(*args)
                rollback_changes.append({'type': 'remove', 'args': args})
            except barbican_exceptions.HTTPClientError as e:
                LOG.info('Unable to register consumer for %s: %s',
                         container_ref, e)
        instance.db_info.save()
        return rollback_changes

    def apply_ssl_state(self, instance, mode, container_ref, enable, disable):
        if enable:
            return self.enable_instance_ssl(instance, mode, container_ref)
        elif disable:
            return self.disable_instance_ssl(instance)

    def rollback_ssl_state(self, instance, old_mode, old_ref,
                           consumer_changes):
        LOG.info('Rolling back ssl state for %s', instance.id)
        instance.db_info.ssl_mode = old_mode
        instance.db_info.ssl_ref = old_ref
        instance.db_info.save()
        for state in reversed(consumer_changes):
            if state['type'] == 'remove':
                self.remove_consumer(*state['args'])
            elif state['type'] == 'register':
                self.register_consumer(*state['args'])


def run_ssl_state_transaction(ssl_client, instances, mode, container_ref,
                              enable, disable, execute, rollback):
    """SSL state change transaction wrapper."""
    states = []
    try:
        # Apply SSL state to DB and Barbican
        for instance in instances:
            state = {
                'instance': instance,
                'mode': instance.db_info.ssl_mode,
                'ref': instance.db_info.ssl_ref}
            state['consumer_changes'] = ssl_client.apply_ssl_state(
                instance, mode, container_ref, enable, disable)
            states.append(state)
        # Execute the wrapped action (guest agent changes)
        result = execute()

    except Exception as e:
        # Rollback all applied states if setup or execution fails
        LOG.exception(
            "Failed to execute SSL action: %s, rolling back states.", e)
        try:
            rollback()
        except Exception as exc:
            LOG.exception(
                "Guest SSL rollback failed, error: %s.", exc)
        for state in reversed(states):
            ssl_client.rollback_ssl_state(
                state['instance'], state['mode'], state['ref'],
                state['consumer_changes'])
        raise

    return result
