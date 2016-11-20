# jdav_lb_webapp

This repository has the purpose to develop a webapplication that can be used by 
JDAV to send newsletters, manage user lists and keep material lists up to date.
As this repository is also meant to be a base for exchange during development, feel free
to contribute ideas in form of edits to this README, issues, landmarks, projects, wiki entries, ...

# Useful stuff

## Reset database for certain app

The following can be useful in case that automatic migrations throw errors.

1. delete everything in the migrations folder except for __init__.py.
2. drop into my MySQL console and do: DELETE FROM django_migrations WHERE app='my_app'
3. while at the MySQL console, drop all of the tables associated with my_app.
4. re-run ./manage.py makemigrations my_app - this generates a 0001_initial.py file in my migrations folder.
5. run ./manage migrate my_app - I expect this command to re-build all my tables, but instead it says: "No migrations to apply."
