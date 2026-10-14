"""``manage.py ensuresuperuser`` — the account a new instance starts with.

Run once from the production entrypoint, before anything else can happen, so
that a fresh deployment has somebody who can log in.

It creates a **member row** for that account as well, and that is not
cosmetic. Permissions in Kompass are held by ``User``s, but everything the
section's own rules reason about is a ``Member``: who may sign a payout off is
resolved by joining ``Member.user`` against the permission, so an account with
no member row holds the capability and is nobody the rules can name. With the
finance rules engine refusing a payout whose eligible group comes out empty —
because an empty group used to be read as "anybody", which let a statement
pay itself out exactly when the rules could not say who should allow it — a
superuser without a member row cannot approve anything through the ordinary
path. That would have been the state of every new instance on its first day.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from members.models import DIVERSE
from members.models import Member


class Command(BaseCommand):
    help = "Creates a super-user non-interactively if it doesn't exist."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write(self.style.WARNING("Superuser data was not set. Skipping."))
            return

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_superuser(username=username, password=password, email=email)
            self.stdout.write(self.style.SUCCESS("Successfully created superuser."))
        else:
            self.stdout.write(
                self.style.SUCCESS("Superuser with configured username already exists. Skipping.")
            )
        self.ensure_member(user, email)

    def ensure_member(self, user, email):
        """Give the account a member row, so the rules can name it.

        Separate from the account check on purpose: an instance whose superuser
        was created before this existed gets its member row the next time this
        command runs, which is what makes running it by hand a repair rather
        than a no-op.
        """
        if Member.objects.filter(user=user).exists():
            return
        Member.objects.create(
            user=user,
            prename=user.get_username()[:20],
            lastname="(Administration)",
            email=email,
            # A role rather than a person, and the field has no default.
            gender=DIVERSE,
        )
        self.stdout.write(self.style.SUCCESS("Created the superuser's member record."))
