# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

import gettext
import os
import subprocess

from setuptools import find_packages
from setuptools.command.sdist import sdist
from setuptools import setup

gettext.install('reddwarf', unicode=1)

from reddwarf.openstack.common.setup import parse_requirements
from reddwarf.openstack.common.setup import parse_dependency_links
from reddwarf.openstack.common.setup import write_requirements
from reddwarf.openstack.common.setup import write_vcsversion
from reddwarf.openstack.common.setup import write_git_changelog

from reddwarf import version


class local_sdist(sdist):
    """Customized sdist hook - builds the ChangeLog file from VC first"""
    def run(self):
        write_git_changelog()
        sdist.run(self)
cmdclass = {'sdist': local_sdist}


try:
    from sphinx.setup_command import BuildDoc

    class local_BuildDoc(BuildDoc):
        def run(self):
            for builder in ['html', 'man']:
                self.builder = builder
                self.finalize_options()
                BuildDoc.run(self)
    cmdclass['build_sphinx'] = local_BuildDoc

except:
    pass


try:
    from babel.messages import frontend as babel
    cmdclass['compile_catalog'] = babel.compile_catalog
    cmdclass['extract_messages'] = babel.extract_messages
    cmdclass['init_catalog'] = babel.init_catalog
    cmdclass['update_catalog'] = babel.update_catalog
except:
    pass

requires = parse_requirements()
depend_links = parse_dependency_links()

write_requirements()
write_vcsversion('reddwarf/vcsversion.py')

setup(name='reddwarf',
    version=version.canonical_version_string(),
    description='PaaS services for Openstack',
    author='OpenStack',
    author_email='openstack@lists.launchpad.net',
    url='http://www.openstack.org/',
    cmdclass=cmdclass,
    packages=find_packages(exclude=['bin']),
    include_package_data=True,
    install_requires=requires,
    dependency_links=depend_links,
    test_suite='nose.collector',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
        ],
    scripts=['bin/reddwarf-server',
             'bin/reddwarf-manage',
             ],
    py_modules=[],
    namespace_packages=['reddwarf'],
)
