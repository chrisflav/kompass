Customization Guide
=================

This guide explains how to customize the Kompass application using configuration files and templates.

Configuration Files
-----------------

The application uses two main configuration files:

* ``settings.toml``: Contains core application settings
* ``text.toml``: Contains customizable text content

settings.toml
~~~~~~~~~~~~

The ``settings.toml`` file contains all core configuration settings organized in sections:

.. code-block:: toml

    [section]
    name = "Your Section Name"
    street = "Street Address"
    town = "12345 Town"
    # ... other section details

    [LJP]
    contribution_per_day = 25
    tax = 0.1

    [finance]
    allowance_per_day = 22
    max_night_cost = 11

Key sections include:

* ``[section]``: Organization details
* ``[LJP]``: Youth leadership program settings
* ``[finance]``: Financial configurations
* ``[misc]``: Miscellaneous application settings
* ``[mail]``: Email configuration
* ``[database]``: Database connection details

Customizing Model Fields
~~~~~~~~~~~~~~~~~~~~~~~

The ``[custom_model_fields]`` section in ``settings.toml`` allows you to customize which fields are visible in the admin interface:

.. code-block:: toml

    [custom_model_fields]
    # Format: applabel_modelname.fields = ['field1', 'field2']
    #         applabel_modelname.exclude = ['field3', 'field4']

    # Example: Show only specific fields
    members_emergencycontact.fields = ['prename', 'lastname', 'phone_number']

    # Example: Exclude specific fields
    members_member.exclude = ['ticket_no', 'dav_badge_no']

There are two ways to customize fields:

1. Using ``fields``: Explicitly specify which fields should be shown
   - Only listed fields will be visible
   - Overrides any existing field configuration
   - Order of fields is preserved as specified

2. Using ``exclude``: Specify which fields should be hidden
   - All fields except the listed ones will be visible
   - Adds to any existing exclusions
   - Original field order is maintained

Field customization applies to:
   - Django admin views
   - Admin forms
   - Model admin fieldsets

.. note::
    Custom forms must be modified manually as they are not affected by this configuration.

Text Content
-----------

The ``text.toml`` file allows customization of application text content:

.. code-block:: toml

    [emails]
    welcome_subject = "Welcome to {section_name}"
    welcome_body = """
    Dear {name},
    Welcome to our organization...
    """

    [messages]
    success_registration = "Registration successful!"

Templates
---------

Template Customization
~~~~~~~~~~~~~~~~~~~~

You can override any template by placing a custom version in your project's templates directory:

1. Create a directory structure matching the original template path
2. Place your custom template file with the same name
3. Django will use your custom template instead of the default

Example directory structure::

    templates/
    └── members/
        └── registration_form.tex
    └── startpage/
        └── contact.html
        └── impressum_content.html


