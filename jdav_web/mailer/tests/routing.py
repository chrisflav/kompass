from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from mailer.routing import LIST
from mailer.routing import PERSONAL
from mailer.routing import resolve
from mailer.routing import sender_allowed
from mailer.routing import split_address
from mailer.routing import strip_detail
from members.models import Group

from .utils import BasicMailerTestCase


class SplitAddressTestCase(BasicMailerTestCase):
    def test_splits_and_lowercases(self):
        self.assertEqual(split_address("Info@Example.ORG"), ("info", "example.org"))

    def test_bare_local_part(self):
        self.assertEqual(split_address("info"), ("info", ""))

    def test_empty(self):
        self.assertEqual(split_address(None), ("", ""))

    def test_strip_detail(self):
        self.assertEqual(strip_detail("bounce+abc123"), ("bounce", "abc123"))
        self.assertEqual(strip_detail("info"), ("info", ""))


class ResolveTestCase(BasicMailerTestCase):
    def test_list_address_collects_members_and_groups(self):
        route = resolve("foobar@{}".format(settings.DOMAIN))
        self.assertEqual(route.kind, LIST)
        self.assertEqual(set(route.targets), {"fritz@foo.com", "paul@foo.com"})
        self.assertEqual(route.address, "foobar@{}".format(settings.DOMAIN))

    def test_list_address_is_case_insensitive(self):
        self.assertIsNotNone(resolve("FooBar"))

    def test_personal_address_resolves_to_single_target(self):
        user = User.objects.create(username="fritz.wulter")
        self.fritz.user = user
        self.fritz.save()

        route = resolve("fritz.wulter")
        self.assertEqual(route.kind, PERSONAL)
        self.assertEqual(route.targets, ("fritz@foo.com",))

    def test_personal_and_list_use_the_same_shape(self):
        """A personal route is just a list route with one target."""
        user = User.objects.create(username="fritz.wulter")
        self.fritz.user = user
        self.fritz.save()

        personal = resolve("fritz.wulter")
        listed = resolve("foobar")
        self.assertEqual(type(personal), type(listed))
        self.assertEqual(len(personal.targets), 1)

    def test_configured_address_wins_over_personal(self):
        user = User.objects.create(username="foobar")
        self.paul.user = user
        self.paul.save()

        self.assertEqual(resolve("foobar").kind, LIST)

    def test_unknown_address(self):
        self.assertIsNone(resolve("nobody"))

    def test_empty_address(self):
        self.assertIsNone(resolve(""))

    def test_user_without_member_is_unknown(self):
        User.objects.create(username="orphan")
        self.assertIsNone(resolve("orphan"))

    def test_list_without_targets_is_unknown(self):
        self.em.to_groups.clear()
        self.em.to_members.clear()
        self.assertIsNone(resolve("foobar"))


class SenderAllowedTestCase(BasicMailerTestCase):
    def test_personal_route_is_unrestricted(self):
        user = User.objects.create(username="fritz.wulter")
        self.fritz.user = user
        self.fritz.save()

        allowed, _reason = sender_allowed(resolve("fritz.wulter"), "stranger@elsewhere.com")
        self.assertTrue(allowed)

    def test_unrestricted_list_accepts_anyone(self):
        allowed, _reason = sender_allowed(resolve("foobar"), "stranger@elsewhere.com")
        self.assertTrue(allowed)

    @override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=["inside.org"])
    def test_internal_only_rejects_outsiders(self):
        self.em.internal_only = True
        self.em.save()

        allowed, reason = sender_allowed(resolve("foobar"), "stranger@elsewhere.com")
        self.assertFalse(allowed)
        self.assertIn("internal", reason)

    @override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=["inside.org"])
    def test_internal_only_accepts_internal_domain(self):
        self.em.internal_only = True
        self.em.save()

        allowed, _reason = sender_allowed(resolve("foobar"), "someone@inside.org")
        self.assertTrue(allowed)

    def test_allowed_senders_restricts_to_group_members(self):
        senders = Group.objects.create(name="Board")
        self.em.allowed_senders.add(senders)

        allowed, reason = sender_allowed(resolve("foobar"), "paul@foo.com")
        self.assertFalse(allowed)
        self.assertIn("group", reason)

        self.paul.group.add(senders)
        allowed, _reason = sender_allowed(resolve("foobar"), "paul@foo.com")
        self.assertTrue(allowed)
