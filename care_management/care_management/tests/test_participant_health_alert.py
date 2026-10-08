import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import ensure_r2c1_participant, ensure_r2c1_user

FIELDS = ["participant","category","severity","concise_summary","response_instruction","supporting_detail","source_type","source_reference","verification_status","verified_by","verified_on","effective_from","effective_to","review_date","status","responsible_role","responsible_user","acknowledgement_required","resolved_by","resolved_on","resolution_reason"]
CASES = [(f"field_{field}", lambda m, f=field: m.has_field(f)) for field in FIELDS]
CASES += [
	("opaque_name", lambda m: m.autoname == "hash"),
	("tracked", lambda m: bool(m.track_changes)),
	("participant_link", lambda m: m.get_field("participant").options == "Participant Profile"),
	("supporting_detail_restricted", lambda m: int(m.get_field("supporting_detail").permlevel or 0) == 1),
	("draft_status", lambda m: "Draft" in m.get_field("status").options),
	("active_status", lambda m: "Active" in m.get_field("status").options),
	("resolved_status", lambda m: "Resolved" in m.get_field("status").options),
	("view_not_ack", lambda m: not m.has_field("viewed_on")),
]


class TestParticipantHealthAlert(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant = ensure_r2c1_participant("R4 Alert", "4234567890")
		self.manager = ensure_r2c1_user("R4 Alert Manager", ["Care Manager"])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_alert(self, **values):
		data = {
			"doctype": "Participant Health Alert", "participant": self.participant,
			"category": "Clinical", "severity": "High", "concise_summary": "R4 test alert",
			"response_instruction": "Follow the current response plan",
			"effective_from": frappe.utils.now_datetime(),
			"review_date": frappe.utils.add_days(frappe.utils.today(), 30),
			"verification_status": "Unverified", "status": "Draft",
		}
		data.update(values)
		return frappe.get_doc(data)

	def test_unverified_alert_cannot_activate(self):
		doc = self.make_alert(status="Active")
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_active_alert_requires_response_and_review_evidence(self):
		frappe.set_user(self.manager)
		for field in ("response_instruction", "effective_from", "review_date"):
			values = {field: None, "verification_status": "Verified", "status": "Active"}
			self.assertRaises(frappe.ValidationError, self.make_alert(**values).insert,
				ignore_permissions=True)

	def test_verification_stamps_actor_and_becomes_immutable(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.verified_by, self.manager)
		self.assertTrue(doc.verified_on)
		doc.concise_summary = "Crafted rewrite"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_verified_alert_cannot_revert(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		doc.verification_status = "Unverified"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_verified_active_alert_cannot_return_to_draft(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		doc.status = "Active"
		doc.save(ignore_permissions=True)
		doc.status = "Draft"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_alert_authoritative_lifecycle_evidence_is_immutable(self):
		doc = self.make_alert().insert(ignore_permissions=True)
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

		doc.reload()
		doc.status = "Resolved"
		doc.resolution_reason = "Resolved by current clinical plan"
		doc.save(ignore_permissions=True)
		for field, value in (
			("resolved_by", "Administrator"),
			("resolved_on", frappe.utils.add_days(doc.resolved_on, 1)),
		):
			fresh = frappe.get_doc(doc.doctype, doc.name)
			fresh.set(field, value)
			self.assertRaises(frappe.PermissionError, fresh.save, ignore_permissions=True)

	def test_resolution_requires_reason_and_stamps_actor(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		doc.status = "Resolved"
		self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)
		doc.reload()
		doc.status = "Resolved"
		doc.resolution_reason = "No longer clinically applicable"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.resolved_by, self.manager)
		self.assertTrue(doc.resolved_on)

	def test_resolved_alert_cannot_reopen_or_rewrite_reason(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		doc.verification_status = "Verified"
		doc.save(ignore_permissions=True)
		doc.status = "Resolved"
		doc.resolution_reason = "Resolved by current clinical plan"
		doc.save(ignore_permissions=True)
		for field, value in (("status", "Active"), ("resolution_reason", "Changed")):
			fresh = frappe.get_doc(doc.doctype, doc.name)
			fresh.set(field, value)
			self.assertRaises(frappe.PermissionError, fresh.save, ignore_permissions=True)

	def test_alert_history_cannot_be_deleted(self):
		doc = self.make_alert().insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, doc.doctype, doc.name,
			ignore_permissions=True)


def _test(predicate):
	def run(self): self.assertTrue(predicate(frappe.get_meta("Participant Health Alert")))
	return run


for _name, _predicate in CASES:
	setattr(TestParticipantHealthAlert, f"test_alert_{_name}", _test(_predicate))
