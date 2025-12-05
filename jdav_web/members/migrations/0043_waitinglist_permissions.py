from django.db import migrations

STANDARD_PERMS = [
    ("members", "view_member"),
    ("members", "view_freizeit"),
    ("members", "add_global_freizeit"),
    ("members", "view_memberwaitinglist"),
    ("members", "view_memberunconfirmedproxy"),
    ("mailer", "view_message"),
    ("mailer", "add_global_message"),
    ("finance", "view_statementunsubmitted"),
    ("finance", "add_global_statementunsubmitted"),
]

FINANCE_PERMS = [
    ("finance", "view_bill"),
    ("finance", "view_ledger"),
    ("finance", "add_ledger"),
    ("finance", "change_ledger"),
    ("finance", "delete_ledger"),
    ("finance", "view_statementsubmitted"),
    ("finance", "view_global_statementsubmitted"),
    ("finance", "change_global_statementsubmitted"),
    ("finance", "view_transaction"),
    ("finance", "change_transaction"),
    ("finance", "add_transaction"),
    ("finance", "delete_transaction"),
    ("finance", "process_statementsubmitted"),
    ("members", "list_global_freizeit"),
    ("members", "view_global_freizeit"),
]

WAITINGLIST_PERMS = [
    ("members", "view_global_memberwaitinglist"),
    ("members", "list_global_memberwaitinglist"),
    ("members", "change_global_memberwaitinglist"),
    ("members", "delete_global_memberwaitinglist"),
]

TRAINING_PERMS = [
    ("members", "change_global_member"),
    ("members", "list_global_member"),
    ("members", "view_global_member"),
    ("members", "add_global_membertraining"),
    ("members", "change_global_membertraining"),
    ("members", "list_global_membertraining"),
    ("members", "view_global_membertraining"),
    ("members", "view_trainingcategory"),
    ("members", "add_trainingcategory"),
    ("members", "change_trainingcategory"),
    ("members", "delete_trainingcategory"),
]

REGISTRATION_PERMS = [
    ("members", "may_manage_all_registrations"),
    ("members", "change_memberunconfirmedproxy"),
    ("members", "delete_memberunconfirmedproxy"),
]

MATERIAL_PERMS = [
    ("members", "list_global_member"),
    ("material", "view_materialpart"),
    ("material", "change_materialpart"),
    ("material", "add_materialpart"),
    ("material", "delete_materialpart"),
    ("material", "view_materialcategory"),
    ("material", "change_materialcategory"),
    ("material", "add_materialcategory"),
    ("material", "delete_materialcategory"),
    ("material", "view_ownership"),
    ("material", "change_ownership"),
    ("material", "add_ownership"),
    ("material", "delete_ownership"),
]


def ensure_group_perms(apps, schema_editor, name, perm_names):
    """
    Ensure the group `name` has the permissions `perm_names`. If the group does not
    exist, create it with the given permissions, otherwise add the missing ones.

    This only adds permissions, already existing ones that are not listed here are not
    removed.
    """
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    perms = [
        Permission.objects.get(codename=codename, content_type__app_label=app_label)
        for app_label, codename in perm_names
    ]
    try:
        g = Group.objects.using(db_alias).get(name=name)
        for perm in perms:
            g.permissions.add(perm)
        g.save()
    # This case is only executed if users have manually removed one of the standard groups.
    except Group.DoesNotExist:  # pragma: no cover
        g = Group.objects.using(db_alias).create(name=name)
        g.permissions.set(perms)
        g.save()


def update_default_permission_groups(apps, schema_editor):
    ensure_group_perms(apps, schema_editor, "Standard", STANDARD_PERMS)
    ensure_group_perms(apps, schema_editor, "Finance", FINANCE_PERMS)
    ensure_group_perms(apps, schema_editor, "Waitinglist", WAITINGLIST_PERMS)
    ensure_group_perms(apps, schema_editor, "Trainings", TRAINING_PERMS)
    ensure_group_perms(apps, schema_editor, "Registrations", REGISTRATION_PERMS)
    ensure_group_perms(apps, schema_editor, "Material", MATERIAL_PERMS)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0010_create_default_permission_groups"),
        ("members", "0042_member_ticket_no"),
    ]

    operations = [
        migrations.RunPython(update_default_permission_groups, migrations.RunPython.noop),
    ]
