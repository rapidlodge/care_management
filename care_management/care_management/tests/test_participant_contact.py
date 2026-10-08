import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import ensure_r2c1_participant, ensure_r2c1_user

CASES = [
	("doctype", lambda m: m.name == "Participant Contact"),
	("opaque_name", lambda m: m.autoname == "hash"),
	("participant_link", lambda m: m.get_field("participant").options == "Participant Profile"),
	("participant_required", lambda m: bool(m.get_field("participant").reqd)),
	("participant_once", lambda m: bool(m.get_field("participant").set_only_once)),
	("type_required", lambda m: bool(m.get_field("contact_type").reqd)),
	("emergency_type", lambda m: "Emergency Contact" in m.get_field("contact_type").options),
	("pharmacist_type", lambda m: "Pharmacist" in m.get_field("contact_type").options),
	("priority_required", lambda m: bool(m.get_field("priority").reqd)),
	("status_required", lambda m: bool(m.get_field("status").reqd)),
	("verification", lambda m: m.has_field("verification_status")),
	("review_date", lambda m: m.has_field("review_date")),
	("availability", lambda m: m.has_field("availability_notes")),
	("unreachable", lambda m: m.has_field("unable_to_reach_instruction")),
	("effective_from", lambda m: m.has_field("effective_from")),
	("effective_to", lambda m: m.has_field("effective_to")),
	("tracked", lambda m: bool(m.track_changes)),
	("no_import", lambda m: not bool(m.allow_import)),
	("no_rename", lambda m: not bool(m.allow_rename)),
	("no_authority_field", lambda m: not any(m.has_field(f) for f in ("consent_authority", "legal_authority", "guardian"))),
]


class TestParticipantContact(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant = ensure_r2c1_participant("R4 Contact", "3234567890")
		self.manager = ensure_r2c1_user("R4 Contact Manager", ["Care Manager"])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_contact(self, **values):
		data = {
			"doctype": "Participant Contact", "participant": self.participant,
			"contact_type": "Emergency Contact", "display_name": "R4 Test Contact",
			"primary_phone": "0400000000", "priority": values.pop("priority", 97),
			"unable_to_reach_instruction": "Escalate to the manager", "status": "Active",
			"verification_status": "Unverified",
		}
		data.update(values)
		return frappe.get_doc(data)

	def test_contact_insert_enforces_emergency_instruction(self):
		doc = self.make_contact(unable_to_reach_instruction="")
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_contact_insert_enforces_positive_priority(self):
		doc = self.make_contact(priority=0)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_active_contact_priority_is_unique(self):
		self.make_contact().insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, self.make_contact(display_name="Other").insert,
			ignore_permissions=True)

	def test_verification_stamps_actor_and_time(self):
		doc = self.make_contact().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.verified_by, self.manager)
		self.assertTrue(doc.verified_on)

	def test_verified_contact_cannot_revert_or_edit_material_evidence(self):
		doc = self.make_contact().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		for field, value in (("verification_status", "Unverified"), ("primary_phone", "0499999999")):
			fresh = frappe.get_doc(doc.doctype, doc.name)
			fresh.set(field, value)
			self.assertRaises(frappe.PermissionError, fresh.save, ignore_permissions=True)

	def test_verified_contact_authoritative_verification_evidence_is_immutable(self):
		doc = self.make_contact().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		for field, value in (
			("verified_by", "Administrator"),
			("verified_on", frappe.utils.add_days(doc.verified_on, 1)),
		):
			fresh = frappe.get_doc(doc.doctype, doc.name)
			fresh.set(field, value)
			self.assertRaises(frappe.PermissionError, fresh.save, ignore_permissions=True)

	def test_verified_inactive_contact_cannot_reactivate_or_delete(self):
		doc = self.make_contact().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		doc.status = "Inactive"
		doc.save(ignore_permissions=True)
		doc.status = "Active"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, doc.doctype, doc.name,
			ignore_permissions=True)


def _test(predicate):
	def run(self):
		self.assertTrue(predicate(frappe.get_meta("Participant Contact")))
	return run


for _name, _predicate in CASES:
	setattr(TestParticipantContact, f"test_contact_{_name}", _test(_predicate))
