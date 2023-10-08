# Copyright 2023 BizflyCloud
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
from unittest import mock

from trove.common import cfg
from trove.guestagent.datastore.mariadb import service
from trove.guestagent.datastore.mysql import service as mysql_service
from trove.guestagent.datastore import service as base_service
from trove.tests.unittests import trove_testtools


CONF = cfg.CONF


class TestService(trove_testtools.TestCase):
    def setUp(self):
        super(TestService, self).setUp()
        _docker_client = mock.MagicMock()
        status = mock.MagicMock()
        self.app = service.MariaDBApp(_docker_client, status)
        self.mysql_app = mysql_service.MySqlApp(_docker_client, status)

    def test_get_backup_image_with_tag(self):
        self.patch_datastore_manager('mariadb')
        CONF.set_override('backup_docker_image',
                          'example.domain/repo/mariadb:tag', 'mariadb')
        image = self.app.get_backup_image()
        self.assertEqual(CONF.mariadb.backup_docker_image, image)

    def test_get_backup_image_without_tag(self):
        self.patch_datastore_manager('mariadb')
        CONF.set_override('backup_docker_image',
                          'example.domain/repo/mariadb', 'mariadb')
        self.patch_conf_property('datastore_version', '10.4')
        image = self.app.get_backup_image()
        _img = f'{CONF.mariadb.backup_docker_image}:{CONF.datastore_version}'
        self.assertEqual(_img, image)

    def test_mysql_backup_image_with_tag(self):
        self.patch_datastore_manager('mysql')
        CONF.set_override('backup_docker_image',
                          'example.domain/repo/mysql:1.1.0', 'mysql')
        self.patch_conf_property('datastore_version', '5.7')
        image = self.mysql_app.get_backup_image()
        self.assertEqual(image, "example.domain/repo/mysql5.7:1.1.0")

    def test_mysql_backup_image_without_tag(self):
        self.patch_datastore_manager('mysql')
        CONF.set_override('backup_docker_image',
                          'example.domain/repo/mysql', 'mysql')
        self.patch_conf_property('datastore_version', '5.7')
        image = self.mysql_app.get_backup_image()
        self.assertEqual(image, "example.domain/repo/mysql:5.7")

    def test_image_has_tag(self):
        fake_values = [
            "example.domain:5000/repo/image_name:tag",
            "example.domain:5000/repo/image-name:tag_tag",
            "example.domain:5000/repo/image_name:tag-tag",
            "example.domain:5000/repo/image-name",
            "example.domain:5000/repo/image_name",
            "example.domain/repo/image-name",
            "example.domain/repo/image-name:tag"]
        self.assertTrue(
            base_service.BaseDbApp._image_has_tag(fake_values[0]))
        self.assertTrue(
            base_service.BaseDbApp._image_has_tag(fake_values[1]))
        self.assertTrue(
            base_service.BaseDbApp._image_has_tag(fake_values[2]))
        self.assertFalse(
            base_service.BaseDbApp._image_has_tag(fake_values[3]))
        self.assertFalse(
            base_service.BaseDbApp._image_has_tag(fake_values[4]))
        self.assertFalse(
            base_service.BaseDbApp._image_has_tag(fake_values[5]))
        self.assertTrue(
            base_service.BaseDbApp._image_has_tag(fake_values[6]))
