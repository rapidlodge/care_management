from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management import participant_identity
from care_management.care_management.participant_identity import (
	is_valid_participant_id,
	resolve_participant_id,
)
from care_management.care_management.tests.helpers import (
	ensure_r2c1_support_plan,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
	make_r4_participant,
)
from care_management.patches.v1_0 import backfill_participant_ids


class TestParticipantIdentity(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_two_participants_cannot_receive_the_same_identifier(self):
		first = make_r4_participant("Unique A").insert(ignore_permissions=True)
		second = make_r4_participant("Unique B").insert(ignore_permissions=True)
		self.assertNotEqual(first.participant_id, second.participant_id)

	def test_unique_database_index_is_the_concurrency_guard(self):
		indexes = frappe.db.sql(
			"""
			select index_name, non_unique
			from information_schema.statistics
			where table_schema = database()
			  and table_name = 'tabParticipant Profile'
			  and column_name = 'participant_id'
			""",
			as_dict=True,
		)
		self.assertTrue(any(not row.non_unique for row in indexes))

	def test_injected_collision_fails_closed_without_partial_record(self):
		candidate = "PTP-" + "1" * 32
		with (
			patch.object(participant_identity, "generate_participant_id", return_value=candidate),
			patch(
				"care_management.care_management.doctype.participant_profile.participant_profile.generate_participant_id",
				return_value=candidate,
			),
		):
			make_r4_participant("Collision A").insert(ignore_permissions=True)
			before = frappe.db.count("Participant Profile")
			self.assertRaises(
				frappe.UniqueValidationError,
				make_r4_participant("Collision B").insert,
				ignore_permissions=True,
			)
			self.assertEqual(frappe.db.count("Participant Profile"), before)

	def test_case_and_separator_variants_are_rejected(self):
		for value in (
			"ptp-" + "a" * 32,
			"PTP_" + "a" * 32,
			"PTP-" + "A" * 32,
			"PTP-" + "a" * 31,
		):
			self.assertFalse(is_valid_participant_id(value))

	def test_permitted_user_resolves_identifier(self):
		doc = make_r4_participant("Resolver Allowed").insert(ignore_permissions=True)
		user = ensure_r2c1_user("R4 Resolver Allowed", ["Care Manager"])
		ensure_r2c1_user_permission(user, doc.name)
		self.assertEqual(resolve_participant_id(doc.participant_id, user=user), doc.name)

	def test_guest_and_unauthorized_user_receive_generic_denial(self):
		doc = make_r4_participant("Resolver Denied").insert(ignore_permissions=True)
		user = ensure_r2c1_user("R4 Resolver Denied", ["Care Manager"])
		self.assertIsNone(resolve_participant_id(doc.participant_id, user="Guest"))
		self.assertIsNone(resolve_participant_id(doc.participant_id, user=user))

	def test_missing_and_malformed_identifiers_fail_closed(self):
		user = ensure_r2c1_user("R4 Resolver Missing", ["Care Manager"])
		for value in (None, "", "PTP-not-valid", "PTP-" + "f" * 32):
			self.assertIsNone(resolve_participant_id(value, user=user))

	def test_conflicting_participant_claim_fails_closed(self):
		candidate = "PTP-" + "2" * 32
		user = ensure_r2c1_user("R4 Resolver Conflict", ["Care Manager"])
		with (
			patch.object(
				frappe.db,
				"get_all",
				return_value=[frappe._dict(name="A"), frappe._dict(name="B")],
			),
			patch.object(
				frappe, "get_doc", side_effect=AssertionError("conflict must fail before document access")
			),
		):
			self.assertIsNone(resolve_participant_id(candidate, user=user))

	def test_backfill_covers_every_eligible_existing_profile(self):
		doc = make_r4_participant("Backfill Complete").insert(ignore_permissions=True)
		frappe.db.set_value("Participant Profile", doc.name, "participant_id", None, update_modified=False)
		self.assertEqual(backfill_participant_ids._backfill_participant_ids(), 1)
		self.assertTrue(
			is_valid_participant_id(frappe.db.get_value("Participant Profile", doc.name, "participant_id"))
		)

	def test_backfill_is_idempotent(self):
		doc = make_r4_participant("Backfill Idempotent").insert(ignore_permissions=True)
		frappe.db.set_value("Participant Profile", doc.name, "participant_id", None, update_modified=False)
		self.assertEqual(backfill_participant_ids._backfill_participant_ids(), 1)
		participant_id = frappe.db.get_value("Participant Profile", doc.name, "participant_id")
		self.assertEqual(backfill_participant_ids._backfill_participant_ids(), 0)
		self.assertEqual(
			frappe.db.get_value("Participant Profile", doc.name, "participant_id"), participant_id
		)

	def test_partial_schema_state_is_safely_resumed(self):
		valid = make_r4_participant("Partial Valid").insert(ignore_permissions=True)
		missing = make_r4_participant("Partial Missing").insert(ignore_permissions=True)
		valid_id = valid.participant_id
		frappe.db.set_value("Participant Profile", missing.name, "participant_id", "", update_modified=False)
		self.assertEqual(backfill_participant_ids._backfill_participant_ids(), 1)
		self.assertEqual(frappe.db.get_value("Participant Profile", valid.name, "participant_id"), valid_id)

	def test_backfill_collision_leaves_all_missing_rows_unassigned(self):
		valid = make_r4_participant("Backfill Collision Existing").insert(ignore_permissions=True)
		missing = make_r4_participant("Backfill Collision Missing").insert(ignore_permissions=True)
		frappe.db.set_value(
			"Participant Profile", missing.name, "participant_id", None, update_modified=False
		)
		with patch.object(
			backfill_participant_ids, "generate_participant_id", return_value=valid.participant_id
		):
			self.assertRaises(frappe.ValidationError, backfill_participant_ids._backfill_participant_ids)
		self.assertFalse(frappe.db.get_value("Participant Profile", missing.name, "participant_id"))

	def test_existing_links_and_document_name_remain_unchanged(self):
		doc = make_r4_participant("Link Stable").insert(ignore_permissions=True)
		plan = ensure_r2c1_support_plan(doc.name, "R4 Link Stable")
		original_name = doc.name
		frappe.db.set_value("Participant Profile", doc.name, "participant_id", None, update_modified=False)
		backfill_participant_ids._backfill_participant_ids()
		self.assertEqual(doc.name, original_name)
		self.assertEqual(frappe.db.get_value("Support Plan", plan, "participant"), original_name)
