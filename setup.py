# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import gettext
import os
import setuptools
import subprocess

gettext.install('reddwarf', unicode=1)

from reddwarf import version
from reddwarf.openstack.common import setup
from reddwarf.openstack.common.setup import write_git_changelog

requires = setup.parse_requirements()
depend_links = setup.parse_dependency_links()


setuptools.setup(
    name='reddwarf',
    version=setup.get_version('reddwarf'),
    description='DBaaS services for Openstack',
    author='OpenStack',
    author_email='openstack@lists.launchpad.net',
    url='https://github.com/stackforge/reddwarf',
    cmdclass=setup.get_cmdclass(),
    packages=setuptools.find_packages(exclude=['bin']),
    include_package_data=True,
    install_requires=requires,
    dependency_links=depend_links,
    setup_requires=['setuptools-git>=0.4'],
    test_suite='nose.collector',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
    ],
    scripts=['bin/reddwarf-api',
             'bin/reddwarf-server',
             'bin/reddwarf-taskmanager',
             'bin/reddwarf-mgmt-taskmanager',
             'bin/reddwarf-manage',
             ],
    py_modules=[],
)
