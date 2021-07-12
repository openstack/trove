.. _testing:

================
Trove Unit Tests
================

Mock Object Library
-------------------

Trove unit tests make a frequent use of the Python Mock library.
This library lets the caller replace (*"mock"*) parts of the system under test with
mock objects and make assertions about how they have been used. [1]_

The Problem of Dangling Mocks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Often one needs to mock global functions in shared system modules.
The caller must restore the original state of the module
after it is no longer required.

Dangling mock objects in global modules (mocked members of imported
modules that never get restored) have been causing various transient
failures in the unit test suite.

The main issues posed by dangling mock objects include::

    - Such object references propagate across the entire test suite. Any
    caller may be hit by a non-functional - or worse - crippled module member
    because some other (potentially totally unrelated) test case failed to
    restore it.

    - Dangling mock references shared across different test modules may
    lead to unexpected results/behavior in multi-threaded environments. One
    example could be a test case failing because a mock got called multiple
    times from unrelated modules.

Such issues are likely to exhibit transient random behavior depending
on the runtime environment, making them difficult to debug.

There are several possible strategies available for dealing with dangling
mock objects (see the section on recommended patterns).
Further information is available in [1]_, [2]_, [3]_.

Dangling Mock Detector
~~~~~~~~~~~~~~~~~~~~~~

All Trove unit tests should extend 'trove_testtools.TestCase'.
It is a subclass of 'testtools.TestCase' which automatically checks for
dangling mock objects at each test class teardown.
It marks the tests as failed and reports the leaked reference if it
finds any.

Writing Unit Tests
------------------
Trove has some legacy unit test code for all the components which is not
recommended to follow. Use the suggested approaches below.

Writing Unit Tests for Trove API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
For trove-api unit test, we use real database (sqlite).

Set up trove database in ``setUpClass`` method.

.. code-block:: python

    from trove.tests.unittests.util import util

    @classmethod
    def setUpClass(cls):
        util.init_db()

and clean up the database in the method ``tearDownClass``:

.. code-block:: python

    from trove.tests.unittests.util import util

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

Insert some data in ``setUpClass`` in order to run the tests.

Trove sends notifications for various operations which communicates with
the message queue service. In unit test, this is also mocked and usually
called in the ``setUp`` method.

.. code-block:: python

    from trove.tests.unittests import trove_testtools

    def setUp(self):
        trove_testtools.patch_notifier(self)

Look at an example in ``trove/tests/unittests/instance/test_service.py``

Run Unit Test
-------------

Run all the unit tests in one command:

.. code-block:: console

   tox -e py38

Run all the tests of a specific test class:

.. code-block:: console

   tox -e py38 -- trove.tests.unittests.instance.test_service.TestInstanceController

Run a single test case:

.. code-block:: console

   tox -e py38 -- trove.tests.unittests.instance.test_service.TestInstanceController.test_create_multiple_versions

References
----------

.. [1] Mock Guide: https://docs.python.org/3/library/unittest.mock.html
.. [2] Python Mock Gotchas: http://alexmarandon.com/articles/python_mock_gotchas/
.. [3] Mocking Mistakes: http://engineroom.trackmaven.com/blog/mocking-mistakes/
