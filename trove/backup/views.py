# Copyright 2013 OpenStack Foundation
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


class BackupView(object):

    def __init__(self, backup):
        self.backup = backup

    def data(self):
        result = {
            "backup": {
                "id": self.backup.id,
                "name": self.backup.name,
                "description": self.backup.description,
                "locationRef": self.backup.location,
                "instance_id": self.backup.instance_id,
                "created": self.backup.created,
                "updated": self.backup.updated,
                "size": self.backup.size,
                "status": self.backup.state,
                "parent_id": self.backup.parent_id,
            }
        }
        if self.backup.datastore_version_id:
            result['backup']['datastore'] = {
                "type": self.backup.datastore.name,
                "version": self.backup.datastore_version.name,
                "version_id": self.backup.datastore_version.id
            }
        return result


class BackupViews(object):

    def __init__(self, backups):
        self.backups = backups

    def data(self):
        backups = []

        for b in self.backups:
            backups.append(BackupView(b).data()["backup"])
        return {"backups": backups}


class BackupStrategyView(object):
    def __init__(self, backup_strategy):
        self.backup_strategy = backup_strategy

    def data(self):
        result = {
            "backup_strategy": {
                "project_id": self.backup_strategy.tenant_id,
                "instance_id": self.backup_strategy.instance_id,
                'backend': self.backup_strategy.backend,
                "swift_container": self.backup_strategy.swift_container,
            }
        }
        return result


class BackupStrategiesView(object):
    def __init__(self, backup_strategies):
        self.backup_strategies = backup_strategies

    def data(self):
        backup_strategies = []
        for item in self.backup_strategies:
            backup_strategies.append(
                BackupStrategyView(item).data()["backup_strategy"])
        return {"backup_strategies": backup_strategies}
