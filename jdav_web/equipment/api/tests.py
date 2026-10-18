"""End-to-end tests for the material REST API, through real OAuth2 bearer tokens."""

import datetime
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import override_settings
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from equipment import services
from equipment.models import CustodyEvent
from equipment.models import Deficit
from equipment.models import Inspection
from equipment.models import Loan
from equipment.models import Part
from equipment.models import Size
from equipment.models import Tag
from equipment.services import Line
from equipment.testing import MaterialFixture
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

BASE = "/api/material"
TODAY = timezone.localdate()


def day(n):
    return TODAY + timedelta(days=n)


def days(n):
    return day(n).isoformat()


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="equipment", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class ApiMixin(MaterialFixture):
    """The fixture, with users and bearer tokens to call the API as each member."""

    def setUp(self):
        self.setUpMaterial()
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.tag = Tag.objects.create(name="Hochtour")
        self.crampon_type.tags.add(self.tag)
        self.users = {}
        for member in (self.alice, self.bob, self.carol):
            user = User.objects.create(username=member.prename.lower())
            member.user = user
            member.save()
            self.users[member.prename.lower()] = user
        self.inventory = self.make_member("Ida")
        self.inventory.user = grant(User.objects.create(username="ida"), "manage_inventory")
        self.inventory.save()
        self.desk = self.make_member("Dirk")
        self.desk.user = grant(User.objects.create(username="dirk"), "manage_lending")
        self.desk.save()
        self.users["ida"] = self.inventory.user
        self.users["dirk"] = self.desk.user
        self.users["nomember"] = User.objects.create(username="nomember")

    def auth(self, name):
        token = AccessToken.objects.create(
            user=self.users[name],
            application=self.application,
            token="tok-{}-{}".format(name, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def get(self, name, path, **params):
        return self.client.get(BASE + path, params, **self.auth(name))

    def post(self, name, path, data=None):
        return self.client.post(
            BASE + path, data=data or {}, content_type="application/json", **self.auth(name)
        )

    def upload(self, name, path, data):
        return self.client.post(BASE + path, data=data, **self.auth(name))

    def patch(self, name, path, data):
        return self.client.patch(
            BASE + path, data=data, content_type="application/json", **self.auth(name)
        )

    def put(self, name, path, data):
        return self.client.put(
            BASE + path, data=data, content_type="application/json", **self.auth(name)
        )

    def delete(self, name, path):
        return self.client.delete(BASE + path, **self.auth(name))

    def image(self, name="a.png", content_type="image/png", size=10):
        return SimpleUploadedFile(name, b"x" * size, content_type=content_type)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MaterialApiTestCase(ApiMixin, TestCase):
    # --- access ----------------------------------------------------------

    def test_requires_a_member(self):
        self.assertEqual(self.client.get(BASE + "/types").status_code, 401)
        self.assertEqual(self.get("nomember", "/types").status_code, 403)

    # --- tags and locations ----------------------------------------------

    def test_tags(self):
        r = self.get("alice", "/categories")
        self.assertEqual(r.json(), [{"id": self.tag.pk, "name": "Hochtour"}])
        r = self.get("alice", "/categories/{}".format(self.tag.pk))
        self.assertEqual(
            r.json()["product_types"], [{"id": self.crampon_type.pk, "name": "Steigeisen"}]
        )
        self.assertEqual(self.post("alice", "/categories", {"name": "Höhle"}).status_code, 403)
        r = self.post("ida", "/categories", {"name": "Höhle"})
        self.assertEqual(r.status_code, 200)
        tag_id = r.json()["id"]
        r = self.put("ida", "/categories/{}".format(tag_id), {"name": "Höhlen"})
        self.assertEqual(r.json()["name"], "Höhlen")
        self.assertEqual(self.delete("ida", "/categories/{}".format(tag_id)).status_code, 200)
        self.assertFalse(Tag.objects.filter(pk=tag_id).exists())

    def test_locations(self):
        r = self.get("alice", "/locations")
        self.assertEqual([loc["name"] for loc in r.json()], ["Griffwerk"])
        r = self.post("ida", "/locations", {"name": "Hessigheim"})
        location_id = r.json()["id"]
        r = self.put(
            "ida", "/locations/{}".format(location_id), {"name": "Hessigheim", "address": "Fels"}
        )
        self.assertEqual(r.json()["address"], "Fels")
        self.assertEqual(self.delete("ida", "/locations/{}".format(location_id)).status_code, 200)
        self.assertEqual(self.post("alice", "/locations", {"name": "X"}).status_code, 403)

    def test_recipients_are_all_members(self):
        names = [m["name"] for m in self.get("alice", "/recipients").json()]
        self.assertIn(self.carol.name, names)
        self.assertIn(self.bob.name, names)

    # --- catalogue -------------------------------------------------------

    def test_catalogue(self):
        services.reserve(self.carol, TODAY, TODAY, [Line(self.crampon_type, 1)])
        r = self.get("alice", "/types")
        cards = {c["name"]: c for c in r.json()}
        self.assertEqual(cards["Steigeisen"]["available"], 1)
        self.assertEqual(cards["Steigeisen"]["available_direct"], 0)
        self.assertEqual(
            cards["Steigeisen"]["groups"],
            [{"id": self.hochtour.pk, "name": "Hochtour", "available": 1, "needs_approval": True}],
        )
        self.assertEqual(cards["Bandschlinge 120 cm"]["groups"][0]["id"], None)
        r = self.get("alice", "/types", start=days(1), end=days(2))
        self.assertEqual({c["name"]: c for c in r.json()}["Steigeisen"]["available"], 2)
        self.assertEqual(
            [c["name"] for c in self.get("alice", "/types", q="hochtour").json()], ["Steigeisen"]
        )
        self.assertEqual(
            [c["name"] for c in self.get("alice", "/types", tag=self.tag.pk).json()], ["Steigeisen"]
        )
        r = self.get("alice", "/types", group=self.jugend.pk)
        self.assertEqual([c["name"] for c in r.json()], ["Gurt"])

    def test_type_detail(self):
        services.reserve(self.carol, day(1), day(2), [Line(self.crampon_type, 1)])
        r = self.get("alice", "/types/{}".format(self.crampon_type.pk))
        data = r.json()
        self.assertIsNone(data["parts"])
        self.assertEqual(data["calendar"][0]["count"], 1)
        self.assertEqual(data["calendar"][0]["borrower"]["name"], "Carol Test")
        r = self.get("ida", "/types/{}".format(self.crampon_type.pk), start=days(1))
        self.assertEqual(len(r.json()["parts"]), 2)
        self.assertEqual(r.json()["available"], 1)

    def test_type_editing(self):
        r = self.post(
            "ida", "/types", {"name": "Pickel", "tags": [self.tag.pk], "daily_rate": "2.50"}
        )
        self.assertEqual(r.status_code, 200)
        type_id = r.json()["id"]
        self.assertEqual(r.json()["tags"], [{"id": self.tag.pk, "name": "Hochtour"}])
        r = self.patch("ida", "/types/{}".format(type_id), {"manufacturer": "Grivel", "tags": []})
        self.assertEqual((r.json()["manufacturer"], r.json()["tags"]), ("Grivel", []))
        r = self.upload("ida", "/types/{}/photo".format(type_id), {"photo": self.image()})
        self.assertTrue(r.json()["photo"])
        pdf = SimpleUploadedFile("m.pdf", b"%PDF", content_type="application/pdf")
        r = self.upload("ida", "/types/{}/manual".format(type_id), {"manual": pdf})
        self.assertTrue(r.json()["manual"])
        r = self.upload("ida", "/types/{}/manual".format(type_id), {"manual": self.image()})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.delete("ida", "/types/{}".format(type_id)).status_code, 200)
        r = self.delete("ida", "/types/{}".format(self.sling_type.pk))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json()["displayable"])
        self.assertEqual(self.post("alice", "/types", {"name": "X"}).status_code, 403)

    def test_upload_limits(self):
        path = "/types/{}/photo".format(self.sling_type.pk)
        r = self.upload("ida", path, {"photo": self.image(content_type="text/plain")})
        self.assertEqual(r.status_code, 422)
        with patch("equipment.api.router.MAX_PHOTO_SIZE", 5):
            self.assertEqual(self.upload("ida", path, {"photo": self.image()}).status_code, 422)
        with patch("equipment.api.router.MAX_MANUAL_SIZE", 2):
            pdf = SimpleUploadedFile("m.pdf", b"%PDF", content_type="application/pdf")
            r = self.upload("ida", "/types/{}/manual".format(self.sling_type.pk), {"manual": pdf})
            self.assertEqual(r.status_code, 422)

    # --- pieces ----------------------------------------------------------

    def test_part_list_is_for_the_material_team(self):
        self.assertEqual(self.get("alice", "/parts").status_code, 403)
        services.lend(self.alice, [self.slings[0]], self.alice, due=TODAY)
        r = self.get("dirk", "/parts", product_type=self.sling_type.pk)
        rows = {row["id"]: row for row in r.json()}
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[self.slings[0].pk]["lent_until"], TODAY.isoformat())
        self.assertEqual(len(self.get("ida", "/parts", q="G1").json()), 1)
        self.slings[1].status = Part.RETIRED
        self.slings[1].save()
        self.assertEqual(len(self.get("ida", "/parts", product_type=self.sling_type.pk).json()), 3)
        self.assertEqual(len(self.get("ida", "/parts", status="retired").json()), 1)

    def test_lookup(self):
        self.slings[1].serial_number = "B77"
        self.slings[1].parent = self.slings[0]
        self.slings[1].save()
        r = self.get("alice", "/parts/lookup", code=" g1 ")
        self.assertEqual(r.json()["id"], self.harness.pk)
        self.assertIsNone(r.json()["custody"])
        r = self.get("alice", "/parts/lookup", code="b77")
        self.assertEqual(r.json()["id"], self.slings[0].pk)
        self.assertEqual(r.json()["components"][0]["label"], "B77")
        r = self.get("alice", "/parts/lookup", code="#{}".format(self.slings[2].pk))
        self.assertEqual(r.json()["holder"]["name"], "Bob Test")
        self.assertEqual(self.get("alice", "/parts/lookup", code="nope").status_code, 422)

    def test_part_detail(self):
        services.reserve(self.alice, day(1), day(2), [Line(part=self.harness)])
        services.inspect(self.harness, Inspection.OK, self.inventory)
        services.transfer([self.harness], self.inventory, member=self.bob)
        CustodyEvent.objects.create(part=self.harness, kind=CustodyEvent.TRANSFER)
        r = self.get("ida", "/parts/{}".format(self.harness.pk))
        data = r.json()
        self.assertEqual(data["custody"][0]["to_name"], None)
        self.assertEqual(
            (data["custody"][1]["from_name"], data["custody"][1]["to_name"]),
            ("Griffwerk", "Bob Test"),
        )
        self.assertEqual(data["reservations"][0]["borrower"]["name"], "Alice Test")
        self.assertEqual(data["inspections"][0]["result"], "ok")
        self.assertEqual(data["inspections"][0]["inspector"]["name"], "Ida Test")
        self.assertEqual(data["next_inspection"], (TODAY + timedelta(days=365)).isoformat())
        self.slings[2].parent = self.slings[0]
        self.slings[2].save()
        r = self.get("ida", "/parts/{}".format(self.slings[2].pk))
        self.assertEqual(r.json()["parent"]["id"], self.slings[0].pk)

    def test_create_parts(self):
        r = self.post(
            "ida",
            "/parts",
            {"product_type": self.sling_type.pk, "count": 3, "home_location": self.cupboard.pk},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 3)
        self.assertEqual(r.json()[0]["location"]["name"], "Griffwerk")
        r = self.post(
            "ida",
            "/parts",
            {
                "product_type": self.harness_type.pk,
                "psa_id": "G2",
                "manufactured_on": "2025-01-01",
                "group": self.jugend.pk,
                "parent": self.slings[0].pk,
            },
        )
        self.assertEqual(r.json()[0]["group"]["name"], "Jugend")
        self.assertEqual(Part.objects.get(psa_id="G2").parent, self.slings[0])
        r = self.post("ida", "/parts", {"product_type": self.harness_type.pk})
        self.assertEqual(r.status_code, 422)
        r = self.post("ida", "/parts", {"product_type": self.sling_type.pk, "count": 0})
        self.assertEqual(r.status_code, 422)
        r = self.post(
            "ida", "/parts", {"product_type": self.sling_type.pk, "count": 2, "serial_number": "S"}
        )
        self.assertEqual(r.status_code, 422)
        r = self.post("alice", "/parts", {"product_type": self.sling_type.pk})
        self.assertEqual(r.status_code, 403)

    def test_update_part(self):
        path = "/parts/{}".format(self.slings[0].pk)
        r = self.patch("ida", path, {"note": "neu", "psa_id": "", "home_location": None})
        self.assertEqual(
            (r.json()["note"], r.json()["psa_id"], r.json()["home_location"]), ("neu", None, None)
        )
        r = self.patch("ida", path, {"parent": self.slings[1].pk})
        self.assertEqual(r.json()["parent"]["id"], self.slings[1].pk)
        r = self.patch("ida", path, {"parent": None})
        self.assertIsNone(r.json()["parent"])
        r = self.upload("ida", path + "/photo", {"photo": self.image()})
        self.assertTrue(r.json()["photo"])
        r = self.patch("ida", "/parts/{}".format(self.harness.pk), {"psa_id": ""})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.patch("alice", path, {"note": "x"}).status_code, 403)

    def test_inspections(self):
        path = "/parts/{}/inspections".format(self.harness.pk)
        r = self.upload("ida", path, {"result": "ok", "date": "2026-01-02", "photo": self.image()})
        self.assertEqual(r.json()["date"], "2026-01-02")
        self.assertTrue(r.json()["photo"])
        r = self.upload("ida", path, {"result": "retired", "comment": "Sturz"})
        self.assertEqual(r.json()["result"], "retired")
        self.assertEqual(self.upload("ida", path, {"result": "ok"}).status_code, 422)
        self.assertEqual(self.upload("alice", path, {"result": "ok"}).status_code, 403)

    def test_psa_register(self):
        self.assertEqual(self.get("alice", "/psa").status_code, 403)
        undated = self.make_part(self.harness_type)
        rows = self.get("ida", "/psa").json()
        self.assertEqual([r["id"] for r in rows], [self.harness.pk, undated.pk])
        self.assertTrue(rows[1]["incomplete"])
        self.assertLess(rows[0]["days_left"], 0)
        services.inspect(self.harness, Inspection.RETIRED, self.inventory)
        self.assertEqual(
            [r["id"] for r in self.get("ida", "/psa", retired=True).json()], [self.harness.pk]
        )

    def test_transfer(self):
        r = self.post(
            "bob", "/parts/transfer", {"parts": [self.slings[2].pk], "location": self.cupboard.pk}
        )
        self.assertEqual(r.json(), {"warnings": []})
        r = self.post(
            "bob", "/parts/transfer", {"parts": [self.harness.pk], "member": self.carol.pk}
        )
        self.assertEqual(r.status_code, 200)
        r = self.post(
            "alice", "/parts/transfer", {"parts": [self.slings[0].pk], "member": self.alice.pk}
        )
        self.assertEqual(r.status_code, 403)
        r = self.post(
            "dirk", "/parts/transfer", {"parts": [self.slings[0].pk], "member": self.alice.pk}
        )
        self.assertEqual(r.status_code, 200)
        r = self.post("dirk", "/parts/transfer", {"parts": [0], "member": self.alice.pk})
        self.assertEqual(r.status_code, 422)
        r = self.post(
            "dirk",
            "/parts/transfer",
            {"parts": [self.slings[2].pk], "member": self.alice.pk, "due": days(2)},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("alice", "/loans").json()[0]["due"], days(2))

    # --- reservations ----------------------------------------------------

    def test_check_and_reserve(self):
        body = {
            "start": days(1),
            "end": days(2),
            "lines": [
                {"product_type": self.crampon_type.pk, "quantity": 1},
                {"part": self.harness.pk},
                {"product_type": self.sling_type.pk, "quantity": 0},
                {},
            ],
        }
        r = self.post("alice", "/reservations/check", body)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(
            r.json()["approval_groups"], [{"id": self.hochtour.pk, "name": "Hochtour"}]
        )
        r = self.post("alice", "/reservations", body)
        self.assertEqual(r.json()["status"], "requested")
        self.assertEqual(len(r.json()["lines"]), 2)
        self.assertEqual(r.json()["decidable_groups"], [])
        r = self.post("alice", "/reservations", body)
        self.assertEqual(r.status_code, 422)
        self.assertIn("errors", r.json())

    def test_reserving_for_others_needs_the_desk(self):
        body = {
            "start": days(1),
            "end": days(1),
            "lines": [{"part": self.harness.pk}],
            "borrower": self.bob.pk,
        }
        self.assertEqual(self.post("alice", "/reservations", body).status_code, 403)
        r = self.post("dirk", "/reservations", body)
        self.assertEqual(r.json()["borrower"]["name"], "Bob Test")
        body["borrower"] = self.alice.pk
        self.assertEqual(self.post("alice", "/reservations/check", body).status_code, 200)

    def test_list_and_view_reservations(self):
        mine = services.reserve(self.alice, day(1), day(2), [Line(self.crampon_type, 1)])
        services.reserve(self.bob, day(1), day(2), [Line(self.sling_type, 1)])
        self.assertEqual([r["id"] for r in self.get("alice", "/reservations").json()], [mine.pk])
        rows = self.get("carol", "/reservations", scope="approvals").json()
        self.assertEqual([r["id"] for r in rows], [mine.pk])
        self.assertEqual(rows[0]["decidable_groups"], [self.hochtour.pk])
        self.assertEqual(self.get("alice", "/reservations", scope="all").status_code, 403)
        self.assertEqual(len(self.get("dirk", "/reservations", scope="all").json()), 2)
        r = self.get(
            "dirk",
            "/reservations",
            scope="all",
            status="requested",
            product_type=self.crampon_type.pk,
        )
        self.assertEqual(len(r.json()), 1)
        path = "/reservations/{}".format(mine.pk)
        self.assertEqual(self.get("alice", path).status_code, 200)
        self.assertEqual(self.get("carol", path).status_code, 200)
        self.assertEqual(self.get("dirk", path).status_code, 200)
        self.assertEqual(self.get("bob", path).status_code, 403)

    def test_cancel_and_decide(self):
        reservation = services.reserve(self.alice, day(1), day(2), [Line(self.crampon_type, 1)])
        path = "/reservations/{}".format(reservation.pk)
        self.assertEqual(
            self.post(
                "bob", path + "/decide", {"group": self.hochtour.pk, "approved": True}
            ).status_code,
            403,
        )
        r = self.post(
            "carol",
            path + "/decide",
            {"group": self.hochtour.pk, "approved": True, "comment": "ok"},
        )
        self.assertEqual(r.json()["status"], "confirmed")
        self.assertEqual(r.json()["approvals"][0]["decided_by"]["name"], "Carol Test")
        self.assertEqual(self.post("bob", path + "/cancel").status_code, 403)
        self.assertEqual(self.post("alice", path + "/cancel").json()["status"], "cancelled")
        other = services.reserve(self.bob, day(1), day(2), [Line(self.sling_type, 1)])
        self.assertEqual(
            self.post("dirk", "/reservations/{}/cancel".format(other.pk)).status_code, 200
        )

    # --- loans -----------------------------------------------------------

    def test_lend_and_return(self):
        r = self.post("alice", "/loans", {"parts": [self.slings[0].pk], "due": days(2)})
        self.assertEqual(r.status_code, 200)
        loan_id = r.json()["id"]
        self.assertFalse(r.json()["overdue"])
        self.assertEqual([loan["id"] for loan in self.get("alice", "/loans").json()], [loan_id])
        self.assertEqual(self.get("alice", "/loans", scope="all").status_code, 403)
        self.assertEqual(len(self.get("dirk", "/loans", scope="all", open=False).json()), 1)
        r = self.post("bob", "/returns", {"parts": [self.slings[0].pk]})
        self.assertEqual(r.status_code, 403)
        r = self.post(
            "alice", "/returns", {"parts": [self.slings[0].pk], "flagged": [self.slings[0].pk]}
        )
        self.assertEqual(r.json(), {"returned": [self.slings[0].pk]})
        self.assertEqual(self.get("alice", "/loans").json(), [])
        r = self.post(
            "dirk", "/returns", {"parts": [self.slings[2].pk], "location": self.cupboard.pk}
        )
        self.assertEqual(r.status_code, 200)

    def test_pickup(self):
        reservation = services.reserve(self.alice, TODAY, day(1), [Line(self.sling_type, 1)])
        piece = reservation.parts.get()
        r = self.post("bob", "/loans", {"parts": [piece.pk], "reservation": reservation.pk})
        self.assertEqual(r.status_code, 403)
        r = self.post("alice", "/loans", {"parts": [piece.pk], "reservation": reservation.pk})
        self.assertEqual(r.json()["reservation"], reservation.pk)
        r = self.post(
            "dirk",
            "/loans",
            {"parts": [self.slings[3].pk], "due": days(1), "borrower": self.bob.pk},
        )
        self.assertEqual(r.json()["borrower"]["name"], "Bob Test")

    def test_receipt(self):
        self.sling_type.daily_rate = "1.50"
        self.sling_type.save()
        loan = services.lend(
            self.alice, [self.slings[0], self.harness], self.alice, due=TODAY + timedelta(days=1)
        )
        path = "/loans/{}/receipt".format(loan.pk)
        self.assertEqual(self.get("bob", path).status_code, 403)
        with patch("equipment.api.router.render_tex", return_value=HttpResponse("pdf")) as render:
            self.assertEqual(self.get("alice", path).status_code, 200)
        context = render.call_args.args[2]
        self.assertEqual(context["days"], 2)
        self.assertEqual(str(context["total"]), "3.00")
        self.assertIsNone(context["rows"][1]["amount"])

    # --- overviews -------------------------------------------------------

    def test_mine(self):
        services.lend(self.alice, [self.slings[0]], self.alice, due=TODAY)
        loan = services.lend(
            self.alice, [self.slings[1]], self.alice, due=TODAY + timedelta(days=3)
        )
        loan.due = TODAY - timedelta(days=1)
        loan.save()
        services.transfer([self.slings[2]], self.bob, member=self.alice)
        services.reserve(self.alice, day(1), day(2), [Line(self.crampon_type, 1)])
        data = self.get("alice", "/mine").json()
        self.assertEqual(
            [p["id"] for p in data["held"]],
            [self.slings[1].pk, self.slings[0].pk, self.slings[2].pk],
        )
        self.assertTrue(data["held"][0]["overdue"])
        self.assertIsNone(data["held"][2]["due"])
        self.assertEqual(len(data["reservations"]), 1)
        self.assertEqual(self.get("carol", "/mine").json()["to_decide"], 1)

    def test_desk(self):
        self.assertEqual(self.get("alice", "/desk").status_code, 403)
        services.reserve(self.alice, TODAY, day(1), [Line(self.sling_type, 1)])
        services.reserve(self.alice, day(1), day(2), [Line(self.crampon_type, 1)])
        services.lend(self.bob, [self.slings[2]], self.bob, due=TODAY)
        overdue = services.lend(self.carol, [self.slings[3]], self.carol, due=TODAY)
        overdue.due = TODAY - timedelta(days=1)
        overdue.save()
        services.return_parts([self.slings[0]], self.inventory, flagged=[self.slings[0]])
        data = self.get("dirk", "/desk").json()
        self.assertEqual(len(data["pickups"]), 1)
        self.assertEqual(len(data["due"]), 1)
        self.assertEqual(len(data["overdue"]), 1)
        self.assertTrue(data["overdue"][0]["overdue"])
        self.assertEqual(len(data["requests"]), 1)
        self.assertEqual([p["id"] for p in data["inspection_due"]], [self.slings[0].pk])

    # --- deficits --------------------------------------------------------

    def test_deficits(self):
        r = self.post(
            "alice", "/deficits", {"product_type": self.crampon_type.pk, "wanted_from": days(3)}
        )
        self.assertEqual(r.json()["product_type"]["name"], "Steigeisen")
        self.assertEqual(self.post("alice", "/deficits", {"text": " "}).status_code, 422)
        r = self.post("alice", "/deficits", {"text": "Seilsack"})
        self.assertEqual(r.json()["reported_by"]["name"], "Alice Test")
        self.assertEqual(self.get("alice", "/deficits").status_code, 403)
        self.assertEqual(len(self.get("ida", "/deficits").json()), 2)
        deficit = Deficit.objects.get(text="Seilsack")
        r = self.patch("ida", "/deficits/{}".format(deficit.pk), {"status": "ordered"})
        self.assertEqual(r.json()["status"], "ordered")
        self.assertEqual(len(self.get("ida", "/deficits").json()), 1)
        self.assertEqual(len(self.get("ida", "/deficits", status="").json()), 2)
        r = self.patch("ida", "/deficits/{}".format(deficit.pk), {"status": "lost"})
        self.assertEqual(r.status_code, 422)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class SizeApiTestCase(ApiMixin, TestCase):
    """Types kept by size: their stock, reservations, loans and returns."""

    def setUp(self):
        super().setUp()
        self.setUpSizes()

    def test_catalogue_and_detail(self):
        services.reserve(self.bob, day(1), day(1), [Line(size=self.size2, quantity=2)])
        cards = {c["name"]: c for c in self.get("alice", "/types", start=days(1)).json()}
        card = cards["Friends"]
        self.assertEqual((card["total"], card["available"], card["sets"]), (6, 4, 0))
        self.assertEqual([s["available"] for s in card["sizes"]], [2, 1, 1])
        self.assertEqual(card["groups"][1]["name"], "Hochtour")
        r = self.get("alice", "/types", group=self.hochtour.pk)
        self.assertIn("Friends", [c["name"] for c in r.json()])
        data = self.get("alice", "/types/{}".format(self.friends_type.pk)).json()
        self.assertEqual(data["calendar"][0]["count"], 2)
        self.assertEqual(len(self.get("alice", "/sizes").json()), 3)

    def test_editing(self):
        path = "/types/{}/sizes".format(self.friends_type.pk)
        self.assertEqual(self.post("alice", path, {"name": "4"}).status_code, 403)
        r = self.post("ida", path, {"name": "4", "quantity": 2, "group": self.jugend.pk})
        self.assertEqual((r.json()["name"], r.json()["group"]["name"]), ("4", "Jugend"))
        size_id = r.json()["id"]
        r = self.patch(
            "ida", "/sizes/{}".format(size_id), {"quantity": 3, "location": self.cupboard.pk}
        )
        self.assertEqual((r.json()["quantity"], r.json()["location"]["name"]), (3, "Griffwerk"))
        self.assertEqual(self.delete("ida", "/sizes/{}".format(size_id)).status_code, 200)
        self.assertFalse(Size.objects.filter(pk=size_id).exists())
        services.reserve(self.alice, day(1), day(1), [Line(size=self.size1)])
        r = self.delete("ida", "/sizes/{}".format(self.size1.pk))
        self.assertEqual(r.status_code, 422)

    def test_reserve_lend_and_return(self):
        body = {"start": days(0), "end": days(1), "lines": [{"size": self.size1.pk, "quantity": 2}]}
        r = self.post("alice", "/reservations/check", body)
        self.assertEqual(r.json()["sizes"][0]["quantity"], 2)
        r = self.post("alice", "/reservations", body)
        reservation = r.json()
        self.assertEqual(reservation["sizes"][0]["size"]["name"], "1")
        r = self.get("alice", "/reservations", product_type=self.friends_type.pk)
        self.assertEqual(len(r.json()), 1)
        r = self.post(
            "alice",
            "/loans",
            {
                "reservation": reservation["id"],
                "sizes": [{"size": self.size1.pk, "quantity": 2}],
            },
        )
        loan = r.json()
        self.assertEqual(loan["sizes"][0]["quantity"], 2)
        self.assertEqual(len(self.get("alice", "/loans").json()), 1)
        held = self.get("alice", "/mine").json()["held_sizes"]
        self.assertEqual((held[0]["quantity"], held[0]["overdue"]), (2, False))
        lent = {"lent": held[0]["id"], "quantity": 1}
        self.assertEqual(self.post("bob", "/returns", {"sizes": [lent]}).status_code, 403)
        self.assertEqual(self.post("alice", "/returns", {"sizes": [lent]}).status_code, 200)
        self.assertEqual(self.get("alice", "/mine").json()["held_sizes"][0]["quantity"], 1)
        self.assertEqual(len(self.get("dirk", "/desk").json()["due"]), 0)
        self.assertEqual(self.post("dirk", "/returns", {"sizes": [lent]}).status_code, 200)
        self.assertEqual(self.get("alice", "/loans").json(), [])

    def test_receipt(self):
        self.friends_type.daily_rate = "2.00"
        self.friends_type.save()
        loan = services.lend(self.alice, [], self.alice, due=TODAY, sizes=[(self.size2, 2)])
        with patch("equipment.api.router.render_tex", return_value=HttpResponse("pdf")) as render:
            self.get("alice", "/loans/{}/receipt".format(loan.pk))
        context = render.call_args.args[2]
        self.assertEqual(context["rows"][0]["part"], "2 × Friends 2")
        self.assertEqual(str(context["total"]), "4.00")

    def test_hand_over_sizes(self):
        body = {"sizes": [{"size": self.size1.pk, "quantity": 1}], "member": self.bob.pk}
        r = self.post("alice", "/parts/transfer", {**body, "due": days(1)})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.post("dirk", "/parts/transfer", body).status_code, 422)
        r = self.post("dirk", "/parts/transfer", {**body, "due": days(1)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("bob", "/mine").json()["held_sizes"][0]["quantity"], 1)

    def test_take_for_good(self):
        r = self.post("alice", "/loans", {"parts": [self.slings[0].pk], "permanent": True})
        self.assertEqual((r.status_code, r.json()), (200, None))
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].holder, self.alice)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LendingRulesApiTestCase(ApiMixin, TestCase):
    """Who may take, pass on and hand back what."""

    def setUp(self):
        super().setUp()
        self.setUpSizes()

    def test_taking_another_groups_material_needs_approval(self):
        body = {"parts": [self.crampons[0].pk], "due": days(3)}
        r = self.post("alice", "/loans", body)
        self.assertEqual(r.status_code, 422)
        self.assertIn("belongs to Hochtour", r.json()["detail"][0])
        r = self.post("alice", "/loans", {"parts": [self.crampons[0].pk], "permanent": True})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.post("carol", "/loans", body).status_code, 200)
        r = self.post(
            "dirk",
            "/loans",
            {"parts": [self.crampons[1].pk], "due": days(3), "borrower": self.alice.pk},
        )
        self.assertEqual(r.status_code, 200)

    def test_picking_up_an_approved_request(self):
        reservation = services.reserve(self.alice, TODAY, day(2), [Line(self.crampon_type, 1)])
        services.decide(reservation, self.hochtour, True, self.carol)
        piece = reservation.parts.get()
        r = self.post("alice", "/loans", {"parts": [piece.pk], "reservation": reservation.pk})
        self.assertEqual(r.status_code, 200)

    def test_a_borrower_cannot_keep_a_loan_by_handing_it_to_themselves(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=day(3))
        body = {"parts": [self.slings[0].pk], "member": self.alice.pk}
        r = self.post("alice", "/parts/transfer", body)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(
            self.post("alice", "/parts/transfer", {**body, "due": days(9)}).status_code, 422
        )
        self.assertTrue(loan.is_open)
        # The desk may end a loan by handing a piece over for good.
        self.assertEqual(self.post("dirk", "/parts/transfer", body).status_code, 200)
        self.assertFalse(loan.is_open)
        self.assertFalse(Loan.objects.filter(pk__gt=loan.pk).exists())

    def test_a_lent_piece_passed_on_stays_on_loan(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=day(3))
        r = self.post(
            "alice", "/parts/transfer", {"parts": [self.slings[0].pk], "member": self.carol.pk}
        )
        self.assertEqual(
            r.json()["warnings"], ["{} stays on loan until {}.".format(self.slings[0], day(3))]
        )
        self.assertFalse(loan.is_open)
        self.assertEqual([loan["due"] for loan in self.get("carol", "/loans").json()], [days(3)])
        # Passed on with a date, the loan runs until then.
        r = self.post(
            "carol",
            "/parts/transfer",
            {"parts": [self.slings[0].pk], "member": self.bob.pk, "due": days(5)},
        )
        self.assertEqual(r.json(), {"warnings": []})
        self.assertEqual([loan["due"] for loan in self.get("bob", "/loans").json()], [days(5)])

    def test_only_the_borrower_passes_on_a_lent_piece(self):
        loan = services.lend(self.alice, [self.harness], self.alice, due=day(3))
        body = {"parts": [self.harness.pk], "location": self.cupboard.pk}
        # Bob leads the group that owns it, but Alice has it on loan.
        r = self.post("bob", "/parts/transfer", body)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(loan.is_open)
        # The material team may take it back.
        self.assertEqual(self.post("ida", "/parts/transfer", body).status_code, 200)
        self.assertFalse(loan.is_open)

    def test_returning_needs_a_place(self):
        services.lend(self.carol, [self.crampons[0]], self.carol, due=day(1))
        r = self.post("carol", "/returns", {"parts": [self.crampons[0].pk]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("has no home location", r.json()["detail"][0])

    def test_deleting_a_type_with_a_used_size(self):
        services.reserve(self.alice, day(1), day(1), [Line(size=self.size1)])
        r = self.delete("ida", "/types/{}".format(self.friends_type.pk))
        self.assertEqual(r.status_code, 422)
        self.assertIn("Set its stock to 0", r.json()["detail"][0])

    def test_a_wish_ends_after_it_starts(self):
        r = self.post(
            "alice", "/deficits", {"text": "Seilsack", "wanted_from": days(3), "wanted_to": days(1)}
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("wanted_to", r.json()["errors"])

    def test_receipt_counts_local_days(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=day(1))
        # Half past midnight here is still the day before in UTC.
        loan.out_at = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(0, 30)))
        loan.save()
        with patch("equipment.api.router.render_tex", return_value=HttpResponse("pdf")) as render:
            self.get("alice", "/loans/{}/receipt".format(loan.pk))
        self.assertEqual(render.call_args.args[2]["days"], 2)

    def test_the_loan_of_a_deleted_member(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=TODAY)
        self.alice.delete()
        data = self.get("dirk", "/loans", scope="all").json()
        self.assertEqual([(row["id"], row["borrower"]) for row in data], [(loan.pk, None)])
        self.assertIsNone(self.get("dirk", "/desk").json()["due"][0]["borrower"])
        with patch("equipment.api.router.render_tex", return_value=HttpResponse("pdf")) as render:
            self.assertEqual(self.get("dirk", "/loans/{}/receipt".format(loan.pk)).status_code, 200)
        tex = render_to_string("equipment/loan_receipt.tex", render.call_args.args[2])
        self.assertIn("a deleted member", tex)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class QueryCountApiTestCase(ApiMixin, TestCase):
    """The lists ask the database a fixed number of times, however many rows they show."""

    def setUp(self):
        super().setUp()
        self.setUpSizes()
        self.rows = 0

    def add_row(self):
        i = self.rows
        self.rows += 1
        services.reserve(
            self.alice,
            day(10 * i + 1),
            day(10 * i + 2),
            [Line(self.sling_type, 1), Line(self.crampon_type, 1), Line(size=self.size1)],
        )
        services.lend(self.bob, [self.slings[i]], self.bob, due=TODAY, sizes=[(self.size2, 1)])

    def count(self, name, path, **params):
        headers = self.auth(name)
        with CaptureQueriesContext(connection) as context:
            r = self.client.get(BASE + path, params, **headers)
        self.assertEqual(r.status_code, 200)
        return len(context)

    def counts(self):
        return {
            "reservations": self.count("alice", "/reservations"),
            "all reservations": self.count("dirk", "/reservations", scope="all"),
            "mine": self.count("alice", "/mine"),
            "desk": self.count("dirk", "/desk"),
            "loans": self.count("dirk", "/loans", scope="all"),
            "type": self.count("alice", "/types/{}".format(self.sling_type.pk)),
        }

    def test_queries_do_not_grow_with_rows(self):
        self.add_row()
        one = self.counts()
        self.add_row()
        self.add_row()
        self.assertEqual(len(self.get("alice", "/reservations").json()), 3)
        self.assertEqual(len(self.get("dirk", "/desk").json()["due"]), 3)
        self.assertEqual(self.counts(), one)
