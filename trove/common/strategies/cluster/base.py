# Copyright 2014 eBay Software Foundation
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


class BaseAPIStrategy(object):

    @property
    def cluster_class(self):
        raise NotImplementedError()

    @property
    def cluster_controller_actions(self):
        raise NotImplementedError()

    @property
    def cluster_view_class(self):
        raise NotImplementedError()

    @property
    def mgmt_cluster_view_class(self):
        raise NotImplementedError()


class BaseTaskManagerStrategy(object):

    @property
    def task_manager_api_class(self, context):
        raise NotImplementedError()

    @property
    def task_manager_cluster_tasks_class(self, context):
        raise NotImplementedError()


class BaseGuestAgentStrategy(object):

    @property
    def guest_client_class(self):
        raise NotImplementedError()
