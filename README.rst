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
