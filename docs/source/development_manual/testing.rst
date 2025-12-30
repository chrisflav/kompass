.. _development_manual/testing:

=================
Testing
=================

Every line of python code is covered by tests. The tests are a mixture of unit and integration tests.

Running the full test suite
----------------------------

To run the complete test suite with coverage reporting, run:

.. code-block:: bash

    make test

If you don't want to test on a clean database everytime, you can pass the option ``keepdb=true`` to preserve the
state of the database. This saves some time, because the migrations don't have to be re-applied. Note that
all migrations will be flagged as uncovered in the coverage report.

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

    # Run a specific test method
    make dev test members.tests.basic.MemberTestCase.test_str

This approach is faster because it:

- Uses the existing development environment (no need to build a separate test container)
- Preserves the test database between runs with ``--keepdb``
- Allows you to quickly test specific modules or test cases

Continuous integration
----------------------

The test suite is run by continuous integration on every pull request and every commit on ``main``. If
a test fails or the coverage report detects an uncovered line, the job will fail.
