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

from datetime import datetime
import ipaddress

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID

from trove.common import ssl
from trove.tests.unittests import trove_testtools


class TestCertificateDetails(trove_testtools.TestCase):

    def _certificate(self, extension=None):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'db.example.com')])
        builder = (x509.CertificateBuilder()
                   .subject_name(subject)
                   .issuer_name(subject)
                   .public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(datetime(2020, 1, 1))
                   .not_valid_after(datetime(2030, 1, 1)))
        if extension is not None:
            builder = builder.add_extension(extension, critical=False)
        certificate = builder.sign(key, hashes.SHA256(), default_backend())
        return certificate.public_bytes(Encoding.PEM)

    def test_dns_and_ip_san(self):
        names = x509.SubjectAlternativeName([
            x509.DNSName('db.example.com'),
            x509.UniformResourceIdentifier('https://db.example.com'),
            x509.IPAddress(ipaddress.ip_address('192.0.2.1')),
            x509.DNSName('db.internal')])

        details = ssl.TroveSSL(None).certificate_details(
            self._certificate(names).decode('ascii'))

        self.assertEqual('db.example.com', details['cn'])
        self.assertEqual(datetime(2030, 1, 1), details['expire_at'])
        self.assertEqual(['DNS:db.example.com', 'DNS:db.internal',
                          'IP Address:192.0.2.1'], details['san'])

    def test_no_san(self):
        details = ssl.TroveSSL(None).certificate_details(self._certificate())

        self.assertIsNone(details['san'])

    def test_unsupported_san_does_not_break_certificate_details(self):
        # Each SAN also contains dNSName "db1".
        unsupported_sans = {
            'ediPartyName': '300f8203646231a508a1060c0474657374',
            'x400Address': '30098203646231a3023000'
        }
        for name, value in unsupported_sans.items():
            with self.subTest(name=name):
                san = x509.UnrecognizedExtension(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME,
                    bytes.fromhex(value))
                details = ssl.TroveSSL(None).certificate_details(
                    self._certificate(san))

                self.assertEqual('db.example.com', details['cn'])
                self.assertIsNone(details['san'])
