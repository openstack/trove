============
Contributing
============

Our community welcomes all people interested in open source cloud
computing, and encourages you to join the `OpenStack Foundation
<http://www.openstack.org/join>`_.

If you would like to contribute to the development of OpenStack,
you must follow the steps documented at:

   http://docs.openstack.org/infra/manual/developers.html#development-workflow

Once those steps have been completed, changes to OpenStack
should be submitted for review via the Gerrit tool, following
the workflow documented at:

   http://docs.openstack.org/infra/manual/developers.html#development-workflow

(Pull requests submitted through GitHub will be ignored.)

Bugs should be filed on Launchpad, not GitHub:

   https://bugs.launchpad.net/trove

We welcome all types of contributions, from blueprint designs to
documentation to testing to deployment scripts. The best way to get
involved with the community is to talk with others online or at a
meetup and offer contributions through our processes, the `OpenStack
wiki <http://wiki.openstack.org>`_, blogs, or on IRC at
``#openstack-trove`` on ``irc.freenode.net``.


House Rules
===========

Code Reviews
------------

We value your contribution in reviewing code changes submitted by
others, as this helps increase the quality of the product as well.
The Trove project encourages the guidelines (below).

   - A rating of +1 on a code review is indicated if:

     * It is your opinion that the change, as proposed, should be
       considered for merging.


   - A rating of 0 on a code review is indicated if:

     * The reason why you believe that the proposed change needs
       improvement is merely an opinion,
     * You have a question, or need a clarification from the author,
     * The proposed change is functional but you believe that there is
       a different, better, or more appropriate way in which to
       achieve the end result being sought by the proposed change,
     * There is an issue of some kind with the Commit Message,
       including violations of the Commit Message guidelines,
     * There is a typographical or formatting error in the commit
       message or the body of the change itself,
     * There could be improvements in the test cases provided as part
       of the proposed change.


   - A rating of -1 on a code review is indicated if:

     * The reason why you believe that the proposed change needs
       improvement is irrefutable, or it is a widely shared opinion as
       indicated by a number of +0 comments,
     * The subject matter of the change (not the commit message)
       violates some well understood OpenStack procedure(s),
     * The change contains content that is demonstrably inappropriate,
     * The test cases do not exercise the change(s) being proposed.


Some other reviewing guidelines:

   - In general, when in doubt, a rating of 0 is advised,
   - The code style guidelines accepted by the project are part of
     tox.ini, a violation of some other hacking rule(s), or pep8 is
     not a reason to -1 a change.

Other references:

   - https://wiki.openstack.org/wiki/CodeReviewGuidelines
   - http://docs.openstack.org/infra/manual/developers.html
   - https://wiki.openstack.org/wiki/ReviewChecklist
   - https://wiki.openstack.org/wiki/GitCommitMessages
   - http://docs.openstack.org/developer/hacking/
   - https://review.openstack.org/#/c/116176/

Approving changes
-----------------

The Trove project follows the conventions below in approving changes.

1. In general, two core reviewers must +2 a change before it can be
   approved. In practice this means that coreA can +2 the change, then
   coreB can +2/+A the change and it can be merged.

2. coreA and coreB should belong to different organizations.

3. For requirements changes proposed by the Proposal Bot or
   translations proposed by Zanata, a single core reviewer can review
   and approve the change.

NOTE:

For the remainder of the Newton release cycle, we will relax the above
conventions. These relaxations apply to the master branch only.

We will adopt a practice of lazy consensus for approving all changes
and a single core reviewer can review and approve a change. This could
be done, for example, by allowing all reviewers know that he or she
intends to approve some change or set of changes if there are no
additional negative comments by a certain time definite.

We will however still require that at least one other person review
(and +1 or +2) the change before it can be +A'ed.

Abandoning changes
------------------

At the Trove mid-cycle held in July 2016 we discussed our process for
abandoning changes and concluded that we would adopt the following
process.

1. We will take a more proactive policy towards abandoning changes
   that have not been merged for a long time.

2. A list of changes proposed for abandonment will be presented at a
   weekly meeting and if there is no objection, those changes will be
   abandoned. If the patch sets are associated with bugs, the bugs
   will be unassigned.

3. In general, changes will be proposed for abandonment if the change
   being proposed has either been addressed in some other patch set,
   or if the patch is not being actively maintained by the author and
   there is no available volunteer who will step up to take over the
   patch set.

Trove Documentation
===================

This repository also contains the following OpenStack manual:

* Database Services API Reference

Prerequisites for Building the Documentation
--------------------------------------------
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

Testing
=======

Usage for integration testing
-----------------------------

If you'd like to start up a fake Trove API daemon for integration testing
with your own tool, run:

.. code-block:: bash

    $ ./tools/start-fake-mode.sh

Stop the server with:

.. code-block:: bash

    $ ./tools/stop-fake-mode.sh

Tests
-----

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
