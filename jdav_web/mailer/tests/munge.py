from django.test import SimpleTestCase
from mailer.munge import is_loop
from mailer.munge import munge
from mailer.munge import parse
from mailer.munge import serialize

RAW = b"""From: "Max Mustermann" <max@outside.example>
To: info@club.example
Subject: Frage zum Kurs
Message-ID: <abc@outside.example>
DKIM-Signature: v=1; a=rsa-sha256; d=outside.example; b=deadbeef
Authentication-Results: mx.club.example; spf=pass
Return-Path: <max@outside.example>
Content-Type: text/plain; charset="utf-8"

Hallo, wann faengt der Kurs an?
"""


class MungeTestCase(SimpleTestCase):
    def munged(self, raw=RAW, **kwargs):
        kwargs.setdefault("list_address", "info@club.example")
        kwargs.setdefault("display_suffix", "via Kompass")
        return munge(parse(raw), **kwargs)

    def test_from_becomes_the_list_address(self):
        message = self.munged()
        self.assertIn("info@club.example", message["From"])
        self.assertIn("Max Mustermann via Kompass", message["From"])

    def test_only_one_from_header(self):
        """A second From header would make the message invalid."""
        self.assertEqual(len(self.munged().get_all("From")), 1)

    def test_author_moves_to_reply_to(self):
        self.assertIn("max@outside.example", self.munged()["Reply-To"])

    def test_existing_reply_to_is_preserved(self):
        raw = RAW.replace(b"Subject:", b"Reply-To: team@outside.example\nSubject:")
        message = self.munged(raw)
        self.assertIn("team@outside.example", message["Reply-To"])
        self.assertEqual(len(message.get_all("Reply-To")), 1)

    def test_inherited_signatures_are_stripped(self):
        """They cover the old From and would fail verification."""
        message = self.munged()
        for header in ("DKIM-Signature", "Authentication-Results", "Return-Path"):
            self.assertIsNone(message[header], header)

    def test_original_author_is_recorded(self):
        self.assertIn("max@outside.example", self.munged()["X-Original-From"])

    def test_loop_marker_is_set(self):
        self.assertEqual(self.munged()["X-Loop"], "info@club.example")

    def test_body_is_untouched(self):
        self.assertIn("wann faengt der Kurs an", serialize(self.munged()).decode())

    def test_subject_survives(self):
        self.assertEqual(self.munged()["Subject"], "Frage zum Kurs")

    def test_missing_from_does_not_crash(self):
        raw = RAW.replace(b'From: "Max Mustermann" <max@outside.example>\n', b"")
        message = self.munged(raw)
        self.assertIn("info@club.example", message["From"])

    def test_serialize_uses_crlf(self):
        self.assertIn(b"\r\n", serialize(self.munged()))


class LoopDetectionTestCase(SimpleTestCase):
    def test_own_marker_is_a_loop(self):
        message = parse(RAW.replace(b"Subject:", b"X-Loop: info@club.example\nSubject:"))
        looping, why = is_loop(message, "info@club.example")
        self.assertTrue(looping)
        self.assertEqual(why, "X-Loop")

    def test_marker_comparison_ignores_case(self):
        message = parse(RAW.replace(b"Subject:", b"X-Loop: INFO@CLUB.EXAMPLE\nSubject:"))
        self.assertTrue(is_loop(message, "info@club.example")[0])

    def test_foreign_marker_is_not_a_loop(self):
        message = parse(RAW.replace(b"Subject:", b"X-Loop: other@elsewhere.example\nSubject:"))
        self.assertFalse(is_loop(message, "info@club.example")[0])

    def test_too_many_received_headers(self):
        hops = b"".join(b"Received: from a by b\n" for _ in range(30))
        message = parse(hops + RAW)
        looping, why = is_loop(message, "info@club.example", max_received=25)
        self.assertTrue(looping)
        self.assertIn("Received", why)

    def test_clean_message_is_not_a_loop(self):
        self.assertFalse(is_loop(parse(RAW), "info@club.example")[0])
