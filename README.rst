Trove
--------

Trove is Database as a Service for Open Stack.


=============================
Usage for integration testing
=============================
If you'd like to start up a fake Trove API daemon for integration testing
with your own tool, run:

.. code-block:: bash

    $ ./tools/start-fake-mode.sh

Stop the server with:

.. code-block:: bash

    $ ./tools/stop-fake-mode.sh


======
Tests
======
To run all tests and PEP8, run tox, like so:

.. code-block:: bash

    $ tox

To run just the tests for Python 2.7, run:

.. code-block:: bash

    $ tox -epy27

To run just PEP8, run:

.. code-block:: bash

    $ tox -epep8

To generate a coverage report,run:

.. code-block:: bash

    $ tox -ecover

(note: on some boxes, the results may not be accurate unless you run it twice)

If you want to run only the tests in one file you can use testtools e.g.

.. code-block:: bash

    $ python -m testtools.run trove.tests.unittests.python.module.path

======
Docs
======

This repository contains the following OpenStack manual:

* Database Services API Reference

Prerequisites
-------------
`Apache Maven <http://maven.apache.org/>`_ must be installed to build the
documentation.

To install Maven 3 for Ubuntu 12.04 and later, and Debian wheezy and later::

    apt-get install maven

On Fedora 15 and later::

    yum install maven3

Building
--------
The manuals are in the ``apidocs`` directory.

To build a specific guide, look for a ``pom.xml`` file within a subdirectory,
then run the ``mvn`` command in that directory. For example::

    cd apidocs
    mvn clean generate-sources

The generated PDF documentation file is::

    apidocs/target/docbkx/webhelp/cdb-devguide/cdb-devguide-reviewer.pdf

The root of the generated HTML documentation is::

    apidocs/target/docbkx/webhelp/cdb-devguide/content/index.html

Testing of changes and building of the manual
----------------------------------------------

Install the python tox package and run ``tox`` from the top-level
directory to use the same tests that are done as part of our Jenkins
gating jobs.

If you like to run individual tests, run:

 * ``tox -e checkniceness`` - to run the niceness tests
 * ``tox -e checksyntax`` - to run syntax checks
 * ``tox -e checkdeletions`` - to check that no deleted files are referenced
 * ``tox -e checkbuild`` - to actually build the manual

tox will use the `openstack-doc-tools package
<https://github.com/openstack/openstack-doc-tools>`_ for execution of
these tests. openstack-doc-tools has a requirement on maven for the
build check.


Contributing
============

Our community welcomes all people interested in open source cloud
computing, and encourages you to join the `OpenStack Foundation
<http://www.openstack.org/join>`_.

The best way to get involved with the community is to talk with others online
or at a meetup and offer contributions through our processes, the `OpenStack
wiki <http://wiki.openstack.org>`_, blogs, or on IRC at ``#openstack``
on ``irc.freenode.net``.

We welcome all types of contributions, from blueprint designs to documentation
to testing to deployment scripts.

If you would like to contribute to the documents, please see the
`Documentation HowTo <https://wiki.openstack.org/wiki/Documentation/HowTo>`_.

Bugs
====

Bugs should be filed on Launchpad, not GitHub:

   https://bugs.launchpad.net/openstack-api-site/


Installing
==========
Refer to http://docs.openstack.org to see where these documents are published
and to learn more about the OpenStack project.
