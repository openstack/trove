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

"""Information on users / identities we can hit the services on behalf of.

This code allows tests to grab from a set of users based on the features they
possess instead of specifying exact identities in the test code.

"""


class Requirements(object):
    """Defines requirements a test has of a user."""

    def __init__(self, is_admin=None, services=None):
        self.is_admin = is_admin
        self.services = services or ["trove"]
        # Make sure they're all the same kind of string.
        self.services = [str(service) for service in self.services]

    def satisfies(self, reqs):
        """True if these requirements conform to the given requirements."""
        if reqs.is_admin is not None:  # Only check if it was specified.
            if reqs.is_admin != self.is_admin:
                return False
        for service in reqs.services:
            if service not in self.services:
                return False
        return True

    def __str__(self):
        return "is_admin=%s, services=%s" % (self.is_admin, self.services)


class ServiceUser(object):
    """Represents a user who uses a service.

    Importantly, this represents general information, such that a test can be
    written to state the general information about a user it needs (for
    example, if the user is an admin or not) rather than explicitly list
    users.

    """

    def __init__(self, auth_user=None, auth_key=None, services=None,
                 tenant=None, tenant_id=None, requirements=None):
        """Creates info on a user."""
        self.auth_user = auth_user
        self.auth_key = auth_key
        self.tenant = tenant
        self.tenant_id = tenant_id
        self.requirements = requirements
        self.test_count = 0
        if self.requirements.is_admin is None:
            raise ValueError("'is_admin' must be specified for a user.")

    def __str__(self):
        return ("{ user_name=%s, tenant=%s, tenant_id=%s, reqs=%s, tests=%d }"
                % (self.auth_user, self.tenant, self.tenant_id,
                   self.requirements, self.test_count))


class Users(object):
    """Collection of users with methods to find them via requirements."""

    def __init__(self, user_list):
        self.users = []
        for user_dict in user_list:
            reqs = Requirements(**user_dict["requirements"])
            user = ServiceUser(auth_user=user_dict["auth_user"],
                               auth_key=user_dict["auth_key"],
                               tenant=user_dict["tenant"],
                               tenant_id=user_dict.get("tenant_id", None),
                               requirements=reqs)
            self.users.append(user)

    def find_all_users_who_satisfy(self, requirements, black_list=None):
        """Returns a list of all users who satisfy the given requirements."""
        black_list = black_list or []
        print("Searching for a user who meets requirements %s in our list..."
              % requirements)
        print("Users:")
        for user in self.users:
            print("\t" + str(user))
        print("Black list")
        for item in black_list:
            print("\t" + str(item))
        return (user for user in self.users
                if user.auth_user not in black_list and
                user.requirements.satisfies(requirements))

    def find_user(self, requirements, black_list=None):
        """Finds a user who meets the requirements and has been used least."""
        users = self.find_all_users_who_satisfy(requirements, black_list)
        try:
            user = min(users, key=lambda user: user.test_count)
        except ValueError:  # Raised when "users" is empty.
            raise RuntimeError("The test configuration data lacks a user "
                               "who meets these requirements: %s"
                               % requirements)
        user.test_count += 1
        return user

    def _find_user_by_condition(self, condition):
        users = (user for user in self.users if condition(user))
        try:
            user = min(users, key=lambda user: user.test_count)
        except ValueError:
            raise RuntimeError('Did not find a user with name "%s".' % name)
        user.test_count += 1
        return user

    def find_user_by_name(self, name):
        """Finds a user who meets the requirements and has been used least."""
        condition = lambda user: user.auth_user == name
        return self._find_user_by_condition(condition)

    def find_user_by_tenant_id(self, tenant_id):
        condition = lambda user: user.tenant_id == tenant_id
        return self._find_user_by_condition(condition)
