import re

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.doctype.participant_profile.participant_profile import (
	ParticipantProfile,
)
from care_management.care_management.tests.helpers import (
	assert_care_doctype_metadata,
	make_r4_participant,
	make_r4_sensitive_identity,
)

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Participant Profile",
	"Participant Sensitive Identity",
	"Living Arrangement",
	"Consent Type",
	"Secondary Disability Type",
]


class TestParticipantSensitiveIdentity(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant = (
			make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True).name
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_01_doctype_metadata(self):
		assert_care_doctype_metadata(self, "Participant Sensitive Identity")
		meta = frappe.get_meta("Participant Sensitive Identity")
		self.assertTrue(meta.track_changes)
		self.assertFalse(meta.allow_import)

	def test_02_exact_protected_field_contract(self):
		meta = frappe.get_meta("Participant Sensitive Identity")
		business_fields = {
			field.fieldname
			for field in meta.fields
			if field.fieldtype not in {"Section Break", "Column Break"}
		}
		self.assertEqual(business_fields, {"participant", *ParticipantProfile.PROTECTED_SOURCE_FIELDS})

	def test_03_valid_record_links_canonical_participant(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		self.assertEqual(doc.participant, self.participant)

	def test_04_name_is_opaque_and_not_derived_from_values(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		self.assertRegex(doc.name, r"^[A-Za-z0-9]{10}$")
		for value in (doc.participant, doc.medicare_number, doc.crn_number):
			self.assertNotIn(str(value).lower(), doc.name.lower())

	def test_05_no_competing_participant_identifier_exists(self):
		meta = frappe.get_meta("Participant Sensitive Identity")
		self.assertFalse(meta.has_field("participant_id"))

	def test_06_duplicate_participant_is_rejected(self):
		make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		self.assertRaises(
			frappe.ValidationError,
			make_r4_sensitive_identity(self.participant).insert,
			ignore_permissions=True,
		)

	def test_07_missing_canonical_participant_is_rejected(self):
		doc = make_r4_sensitive_identity("R4-MISSING-CANONICAL")
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_08_participant_link_is_immutable(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		other = make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True)
		doc.participant = other.name
		self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

	def test_09_rename_is_denied(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		self.assertRaises(
			frappe.ValidationError,
			frappe.rename_doc,
			doc.doctype,
			doc.name,
			frappe.generate_hash(length=10),
		)

	def test_10_delete_is_denied(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		self.assertRaises(
			frappe.ValidationError,
			frappe.delete_doc,
			doc.doctype,
			doc.name,
			ignore_permissions=True,
		)

	def test_11_copy_cannot_create_second_record(self):
		doc = make_r4_sensitive_identity(self.participant).insert(ignore_permissions=True)
		copy = frappe.copy_doc(doc)
		self.assertRaises(frappe.ValidationError, copy.insert, ignore_permissions=True)

	def test_12_invalid_medicare_number_is_rejected(self):
		doc = make_r4_sensitive_identity(self.participant, medicare_number="invalid")
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_13_valid_medicare_spacing_is_accepted(self):
		doc = make_r4_sensitive_identity(self.participant, medicare_number="4234 567 890")
		doc.insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists(doc.doctype, doc.name))

	def test_14_interpreter_language_is_conditionally_required(self):
		doc = make_r4_sensitive_identity(
			self.participant,
			interpreter_required="Yes",
			interpreter_language_required=None,
		)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_15_attachments_are_not_part_of_the_contract(self):
		meta = frappe.get_meta("Participant Sensitive Identity")
		self.assertFalse(any(field.fieldtype == "Attach" for field in meta.fields))

	def test_16_later_scope_fields_are_excluded(self):
		meta = frappe.get_meta("Participant Sensitive Identity")
		for fieldname in (
			"mygov_account",
			"primary_disability",
			"risk_or_alert",
			"consent_received",
			"living_arrangements",
			"funding_type",
			"pharmacist_name",
		):
			self.assertFalse(meta.has_field(fieldname))
