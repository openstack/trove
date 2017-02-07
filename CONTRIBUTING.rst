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
     * The test cases do not exercise the change(s) being proposed,
     * The change causes a failure in the pylint job (see pylint
       section below),
     * A user visible change does not provide a release note.

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
   - trove-pylint readme file in tools/trove-pylint.README

Code Review Priority
--------------------

At the design summit in Barcelona (October 2016) we discussed code
review priority. We have a significant number of priorities for what
we want to get merged in each release. As we get closer to the release
date the time crunch will become even more acute. Therefore, we
consciously focus on taking steps to merge changes in a manner
consistent with these priorities.

All contributors to the project can help with this by reviewing the
code submitted by others, and getting them merged in a timely
manner.

Reviewing code is an important community activity and if you would
like others to prioritize the review of your changes, it is strongly
advised that you take the time to review other contributors code, and
provide useful feedback. You will notice that as you review others
code, you will not only learn more about the project and the many
supported databases, but also that others take a more proactive view
to reviewing the changes that you submit.

Merely submitting code and expecting others to review it will (most
likely) not work. If you've submitted code and you find that it isn't
getting reviewed, consider whether you've done your fair share for the
project by reviewing others code, or testing, or documenting, or
submitting significant improvements, or in one of many other ways in
which you can help advance the project.

Approving Changes
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

Launchpad Bugs
--------------

Bugs should be filed on Launchpad at:

    https://bugs.launchpad.net/trove

All changes that address a Launchpad bug should include the bug in the
Commit Message using the Closes-Bug, Related-Bug, or Partial-Bug keyword.

It is not required that a Launchpad bug be filed for every change.

Release Notes
-------------

All user visible changes should include a release note. Trove uses
reno to generate release notes and therefore only those release notes
that are submitted as part of a change will be included in the release
notes. The failure to add a release note for a user visible change
should be identified in review, and corrected.

If a Launchpad bug is being fixed, the release note should list the
bug number.

For help using reno, the release notes tool, see:

    https://wiki.openstack.org/wiki/Trove/create-release-notes-with-reno

Trove Documentation
===================

This repository also contains the Database Services API Reference.
To build the API reference, run::

    $ tox -e api-ref

The generated documentation is found::

    api-ref/html/index.html

Trove PyLint Failures
=====================

The Trove project uses trove-pylint (tools/trove-pylint) in the gate
and this job is intended to help catch coding errors that sometimes
may not get caught in a code review, or by the automated tests.

The gate-trove-tox-pylint jobs are run by the CI, and these invoke the
command in tools/trove-pylint.

The tool can produce false-positive notifications and therefore
supports a mechanism to provide a list of errors that are to be
ignored.

Before submitting a change, please do run

.. code-block:: bash

    $ tox -e pylint

on your development environment. If this fails, you will have to
resolve all the errors before you can commit the code.

This means you either must fix the problem being identified, or
regenerate the list of ignored errors and submit that as part of your
review.

To regenerate the list of ignored errors, you run the command(s):

.. code-block:: bash

    $ tox -e pylint rebuild

Warning: trove-pylint is very sensitive to the version(s) of pylint
and astroid that are installed on your system and for this reason, a
tox environment is provided that will mimic the environment that
pylint will encounter in the gate.

Pre-commit checklist
====================

Before committing code to Gerrit for review, please at least do the
following on your development system and ensure that they pass.

.. code-block:: bash

    $ tox -e pep8
    $ tox -e py27
    $ tox -e py34
    $ tox -e pylint

If you are unable to get these to pass locally, it is a waste of the
CI resources to push up a change for review.


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

Note that some unit tests can use an existing database. The script
``tools/test-setup.sh`` sets up the database for CI jobs and can be
used for local setup.
