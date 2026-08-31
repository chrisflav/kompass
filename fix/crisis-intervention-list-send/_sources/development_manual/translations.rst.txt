.. _development_manual/translations:

============
Translations
============

All text in the source code must be written in English and come with a German translation using
`Django's translation system <https://docs.djangoproject.com/en/stable/topics/i18n/translation/>`_.
This means every user-visible string must be wrapped in a translation function such as
``_("...")`` or ``gettext("...")``, and a corresponding German translation must be provided in the
``.po`` files under ``locale/de/``.

Generating translation files
-----------------------------

After adding or changing translatable strings, the translation files need to be regenerated.
There are two ways to do this depending on your development setup.

Using the development Docker environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the development Docker environment is running, use:

.. code-block:: bash

    make dev translate

Using uv
^^^^^^^^

To run the translation step directly without Docker, use:

.. code-block:: bash

    make uv translate

This requires the project dependencies to be installed first. See
:ref:`development_manual/setup/uv` for details.

After running either command, open the updated ``.po`` files and fill in the German translations
for any newly added strings.

Fuzzy markers
-------------

Django's ``makemessages`` command may mark some strings as *fuzzy* when it detects that an
existing translation is close but not exact. Fuzzy translations are not used at runtime and
must not remain in the committed ``.po`` files. Remove the ``#, fuzzy`` marker and verify the
translation is correct before committing.

Continuous integration enforces that no fuzzy markers are present. See
:ref:`development_manual/ci` for details.
