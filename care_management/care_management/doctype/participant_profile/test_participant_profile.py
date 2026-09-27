# Copyright (c) 2026, Hex Flow and Contributors
# See license.txt

import frappe
from frappe.core.doctype.data_import.data_import import DataImport
from frappe.tests import IntegrationTestCase
from frappe.utils.file_manager import save_file

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

	def test_data_import_cannot_replace_identifier_or_partially_update_profile(self):
		doc = make_r4_participant("Data Import").insert(ignore_permissions=True)
		original_identifier = doc.participant_id
		original_marital_status = doc.marital_status
		replacement_identifier = "PTP-" + "9" * 32
		import_file = None
		data_import = None
		participant_meta = frappe.get_meta("Participant Profile")
		original_allow_import = participant_meta.allow_import

		try:
			content = (
				f"Participant,Participant ID,Marital status\n{doc.name},{replacement_identifier},Married\n"
			)
			import_file = save_file(
				"r4-participant-identifier-immutability.csv",
				content,
				None,
				None,
				is_private=1,
			)

			# Participant Profile is not generally import-enabled. Temporarily expose it to
			# the installed Data Import controller without changing stored metadata.
			participant_meta.allow_import = 1
			data_import = frappe.get_doc(
				{
					"doctype": "Data Import",
					"import_type": "Update Existing Records",
					"reference_doctype": "Participant Profile",
					"import_file": import_file.file_url,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()

			self.assertTrue(DataImport.start_import(data_import))
			data_import.reload()
			logs = frappe.get_all(
				"Data Import Log",
				filters={"data_import": data_import.name},
				fields=["success", "messages", "exception"],
			)

			self.assertEqual(data_import.status, "Error")
			self.assertEqual(len(logs), 1)
			self.assertFalse(logs[0].success)
			self.assertNotIn(original_identifier, frappe.as_json(logs[0]))
			self.assertNotIn(replacement_identifier, frappe.as_json(logs[0]))
			self.assertEqual(
				frappe.db.get_value("Participant Profile", doc.name, "participant_id"),
				original_identifier,
			)
			self.assertEqual(
				frappe.db.get_value("Participant Profile", doc.name, "marital_status"),
				original_marital_status,
			)
		finally:
			participant_meta.allow_import = original_allow_import
			frappe.set_user("Administrator")
			if data_import and frappe.db.exists("Data Import", data_import.name):
				frappe.delete_doc("Data Import", data_import.name, force=True, ignore_permissions=True)
			if import_file and frappe.db.exists("File", import_file.name):
				frappe.delete_doc("File", import_file.name, force=True, ignore_permissions=True)
			if frappe.db.exists("Participant Profile", doc.name):
				frappe.delete_doc("Participant Profile", doc.name, force=True, ignore_permissions=True)
			for doctype, name, child_doctype, child_field in (
				("Consent Type", "R4 Test Consent", "Participant Consent", "consent_type"),
				(
					"Living Arrangement",
					"R4 Test Living Arrangement",
					"Participant Living Arrangement",
					"living_arrangement",
				),
				(
					"Secondary Disability Type",
					"R4 Test Secondary Disability",
					"Participant Secondary Disability",
					"secondary_disability",
				),
			):
				if frappe.db.exists(doctype, name):
					self.assertFalse(frappe.db.exists(child_doctype, {child_field: name}))
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			frappe.db.commit()
