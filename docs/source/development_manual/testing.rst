.. _development_manual/testing:

=================
Testing
=================

Every line of Python code is covered by tests. The tests are a mixture of unit and integration tests.

Running the full test suite
----------------------------

To run the complete test suite with coverage reporting, run:

.. code-block:: bash

    make test

The test command supports several optional parameters:

- ``keepdb=true`` - Preserve the database between test runs (default: false)
- ``verbosity=N`` - Set Django test verbosity level 0-3 (default: 2)
- ``quiet=true`` - Show only master container output, hide other services (default: false)

.. code-block:: bash

    # Run tests with minimal output
    make test verbosity=0 quiet=true

    # Preserve database and use verbosity level 1
    make test keepdb=true verbosity=1

    # Quiet mode to hide database/redis/cache container output
    make test quiet=true

Note: When using ``keepdb=true``, migrations are not re-applied, which saves time but causes
all migrations to be flagged as uncovered in the coverage report.

Running tests during development
---------------------------------

For faster iteration during development, you can run tests in the development Docker environment:

.. code-block:: bash

    # Run all tests
    make dev test

    # Run tests for a specific app
    make dev test members

    # Run a specific test class
    make dev test members.tests.basic.MemberTestCase

    # Run specific test methods
    make dev test members.tests.basic.GroupTestCase.test_str members.tests.basic.MemberTestCase.test_place


By default, the test database is only created once and then reused in follow-up runs. To regenerate
the database, use ``keepdb=false``:

.. code-block:: bash

    make dev test keepdb=false members.tests.basic.GroupTestCase.test_str

After running the tests a coverage report is generated, even if the tests fail.
Keep in mind that when running only a few tests, the coverage report only contains local information.

Continuous integration
----------------------

The test suite is run by continuous integration on every pull request and every commit on ``main``. If
a test fails or the coverage report detects an uncovered line, the job will fail.
