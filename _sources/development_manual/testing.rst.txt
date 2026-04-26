.. _development_manual/testing:

=================
Testing
=================

Every line of python code is covered by tests. The tests are a mixture of unit and integration tests.

To run the test suite locally, run

.. code-block:: bash

    make test

If you don't want to test on a clean database everytime, you can pass the option ``keepdb=true`` to preserve the
state of the database. This saves some time, because the migrations don't have to be re-applied. Note that
all migrations will be flagged as uncovered in the coverage report.

Continuous integration
----------------------

The test suite is run by continuous integration on every pull request and every commit on ``main``. If
a test fails or the coverage report detects an uncovered line, the job will fail.
