# Copyright (c) 2026, Hex Flow and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.participant_identity import is_valid_participant_id
from care_management.care_management.tests.helpers import (
	assert_care_doctype_metadata,
	ensure_r2c1_user,
	make_r4_participant,
)


class TestParticipantProfile(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_doctype_metadata(self):
		assert_care_doctype_metadata(self, "Participant Profile")

	def test_new_profile_receives_one_canonical_identifier(self):
		doc = make_r4_participant("Generated").insert(ignore_permissions=True)
		self.assertTrue(is_valid_participant_id(doc.participant_id))
		self.assertEqual(
			frappe.db.get_value("Participant Profile", doc.name, "participant_id"),
			doc.participant_id,
		)

	def test_identifier_format_is_exact(self):
		participant_id = make_r4_participant("Format").insert(ignore_permissions=True).participant_id
		self.assertEqual(len(participant_id), 36)
		self.assertEqual(participant_id[:4], "PTP-")
		self.assertRegex(participant_id[4:], r"^[0-9a-f]{32}$")

	def test_identifier_contains_no_personal_field_fragment(self):
		doc = make_r4_participant("Personal-Fragment").insert(ignore_permissions=True)
		for value in (doc.participant, doc.medicare_number, doc.crn_number):
			self.assertNotIn(str(value).lower(), doc.participant_id.lower())

	def test_caller_supplied_identifier_is_rejected(self):
		doc = make_r4_participant("Supplied", "PTP-" + "a" * 32)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_desk_style_save_cannot_edit_or_clear_identifier(self):
		doc = make_r4_participant("Desk").insert(ignore_permissions=True)
		for replacement in ("PTP-" + "b" * 32, None):
			doc = frappe.get_doc("Participant Profile", doc.name)
			doc.participant_id = replacement
			self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

	def test_api_style_update_cannot_edit_identifier(self):
		from frappe.client import set_value

		doc = make_r4_participant("API").insert(ignore_permissions=True)
		self.assertRaises(
			frappe.ValidationError,
			set_value,
			"Participant Profile",
			doc.name,
			"participant_id",
			"PTP-" + "c" * 32,
		)

	def test_system_manager_and_administrator_cannot_override_identifier(self):
		doc = make_r4_participant("Privileged").insert(ignore_permissions=True)
		system_manager = ensure_r2c1_user("R4 System Manager", ["System Manager"])
		for user in (system_manager, "Administrator"):
			frappe.set_user(user)
			current = frappe.get_doc("Participant Profile", doc.name)
			current.participant_id = "PTP-" + "d" * 32
			self.assertRaises(frappe.ValidationError, current.save)

	def test_copy_generates_a_distinct_identifier_and_rename_is_not_enabled(self):
		doc = make_r4_participant("Copy Source").insert(ignore_permissions=True)
		copy = frappe.copy_doc(doc, ignore_no_copy=False)
		copy.participant = "R4 Test Participant Copy Target"
		copy.insert(ignore_permissions=True)
		self.assertNotEqual(copy.participant_id, doc.participant_id)
		self.assertRaises(
			frappe.ValidationError, frappe.rename_doc, "Participant Profile", doc.name, "R4 Renamed"
		)
		self.assertEqual(
			frappe.db.get_value("Participant Profile", doc.name, "participant_id"),
			doc.participant_id,
		)

	def test_background_document_save_cannot_replace_identifier(self):
		doc = make_r4_participant("Background").insert(ignore_permissions=True)
		current = frappe.get_doc("Participant Profile", doc.name)
		current.participant_id = "PTP-" + "e" * 32
		self.assertRaises(frappe.ValidationError, current.save, ignore_permissions=True)
