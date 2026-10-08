import frappe
from frappe.tests import IntegrationTestCase
from care_management.care_management import permissions
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_support_task,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)

DOCTYPES = ("Participant Contact", "Participant Health Alert", "Participant Health Alert Acknowledgement")
CASES = []
for dt in DOCTYPES:
	CASES.extend([
		(f"protected_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PROTECTED_PARTICIPANT_DOCTYPES),
		(f"direct_{frappe.scrub(dt)}", lambda d=dt: permissions.DIRECT_PARTICIPANT_FIELDS.get(d) == "participant"),
		(f"query_hook_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PARTICIPANT_PERMISSION_QUERY_CONDITION_HOOKS),
		(f"doc_hook_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PARTICIPANT_DOCUMENT_PERMISSION_HOOKS),
	])
for role in ("Clinical Lead", "Privacy Officer"):
	CASES.extend([
		(f"role_constant_{frappe.scrub(role)}", lambda r=role: r in permissions.CONTACT_ALERT_READ_ROLES),
		(f"not_manager_{frappe.scrub(role)}", lambda r=role: r not in permissions.CARE_MANAGER_ROLES),
	])
CASES += [
	("guest_denied", lambda: permissions.normalize_user("Guest") is None),
	("unknown_denied", lambda: permissions.get_participant_permission_query_conditions("Unknown", "Guest") == "1=0"),
	("contact_worker_scoped", lambda: "Participant Contact" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("alert_worker_scoped", lambda: "Participant Health Alert" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("ack_worker_scoped", lambda: "Participant Health Alert Acknowledgement" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("no_contact_admin_authority", lambda: "Consent" not in permissions.DIRECT_PARTICIPANT_FIELDS.get("Participant Contact", "")),
	("docshare_protected", lambda: all(d in permissions.PROTECTED_PARTICIPANT_DOCTYPES for d in DOCTYPES)),
	("three_targets", lambda: len(DOCTYPES) == 3),
]


class TestParticipantContactAlertPermissions(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R4 Permission A", "5234567890")
		self.participant_b = ensure_r2c1_participant("R4 Permission B", "52345678901")
		self.worker = ensure_r2c1_user("R4 Permission Worker", ["Support Worker"])
		self.other_worker = ensure_r2c1_user("R4 Permission Other Worker", ["Support Worker"])
		self.manager = ensure_r2c1_user("R4 Permission Manager", ["Care Manager"])
		self.privacy = ensure_r2c1_user("R4 Permission Privacy", ["Privacy Officer"])
		ensure_r2c1_user_permission(self.worker, self.participant_a)
		ensure_r2c1_user_permission(self.other_worker, self.participant_b)
		ensure_r2c1_user_permission(self.manager, self.participant_a)
		ensure_r2c1_user_permission(self.privacy, self.participant_a)
		plan = ensure_r2c1_support_plan(self.participant_a, "R4 Permission A")
		task = ensure_r2c1_support_task(plan, "R4 Permission A")
		ensure_r2c1_task_assignment(task, self.worker)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_contact(self, participant, **values):
		verification_status = values.pop("verification_status", "Verified")
		data = {"doctype": "Participant Contact", "participant": participant,
			"contact_type": "Other Operational Contact", "display_name": "Permission fixture",
			"priority": values.pop("priority", 81), "verification_status": "Unverified", "status": "Active",
			"effective_from": frappe.utils.today(), "review_date": frappe.utils.add_days(frappe.utils.today(), 7)}
		data.update(values)
		doc = frappe.get_doc(data).insert(ignore_permissions=True)
		if verification_status == "Verified":
			frappe.db.set_value(doc.doctype, doc.name, "verification_status", "Verified")
			doc.reload()
		return doc

	def make_alert(self, participant, **values):
		verification_status = values.pop("verification_status", "Verified")
		status = values.pop("status", "Active")
		data = {"doctype": "Participant Health Alert", "participant": participant,
			"category": "Safety", "severity": "High", "concise_summary": "Permission fixture",
			"response_instruction": "Use approved response", "verification_status": "Unverified",
			"effective_from": frappe.utils.now_datetime(), "review_date": frappe.utils.add_days(frappe.utils.today(), 7),
			"status": "Draft", "acknowledgement_required": 1}
		data.update(values)
		doc = frappe.get_doc(data).insert(ignore_permissions=True)
		frappe.db.set_value(doc.doctype, doc.name, {"verification_status": verification_status, "status": status})
		doc.reload()
		return doc

	def test_assigned_worker_reads_current_verified_contact_and_alert(self):
		contact = self.make_contact(self.participant_a)
		alert = self.make_alert(self.participant_a)
		self.assertTrue(permissions.has_participant_document_permission(contact, "read", self.worker))
		self.assertTrue(permissions.has_participant_document_permission(alert, "read", self.worker))

	def test_worker_denied_unverified_expired_overdue_and_unassigned_records(self):
		fixtures = [
			self.make_contact(self.participant_a, priority=82, verification_status="Unverified"),
			self.make_contact(self.participant_a, priority=83, effective_to=frappe.utils.add_days(frappe.utils.today(), -1)),
			self.make_contact(self.participant_a, priority=84, review_date=frappe.utils.add_days(frappe.utils.today(), -1)),
			self.make_alert(self.participant_b),
			self.make_alert(self.participant_a, status="Draft", verification_status="Unverified"),
		]
		for doc in fixtures:
			self.assertFalse(permissions.has_participant_document_permission(doc, "read", self.worker))
		unassigned_contact = self.make_contact(self.participant_b, priority=85)
		self.assertFalse(
			permissions.has_participant_document_permission(unassigned_contact, "read", self.other_worker)
		)

	def test_list_query_contains_lifecycle_and_assignment_guards(self):
		contact = permissions.get_participant_permission_query_conditions("Participant Contact", self.worker)
		alert = permissions.get_participant_permission_query_conditions("Participant Health Alert", self.worker)
		self.assertIn("verification_status", contact)
		self.assertIn("review_date", contact)
		self.assertIn("Support Task Assigned Staff", alert)
		self.assertIn("verification_status", alert)

	def test_cross_participant_acknowledgement_attack_fails_without_persistence(self):
		alert = self.make_alert(self.participant_b)
		frappe.set_user(self.worker)
		doc = frappe.get_doc({"doctype": "Participant Health Alert Acknowledgement",
			"health_alert": alert.name, "participant": self.participant_a})
		self.assertFalse(frappe.has_permission(doc.doctype, "create", doc=doc, user=self.worker))
		self.assertRaises(frappe.PermissionError, doc.insert)
		self.assertFalse(frappe.db.exists(doc.doctype, {"health_alert": alert.name, "acknowledged_by": self.worker}))

	def test_acknowledgement_derives_authoritative_participant_and_actor(self):
		alert = self.make_alert(self.participant_a)
		frappe.set_user(self.worker)
		doc = frappe.get_doc({"doctype": "Participant Health Alert Acknowledgement",
			"health_alert": alert.name}).insert()
		self.assertEqual(doc.participant, self.participant_a)
		self.assertEqual(doc.acknowledged_by, self.worker)
		self.assertTrue(doc.alert_version)

	def test_privacy_officer_is_metadata_only_at_field_permission_layer(self):
		for doctype, restricted in {
			"Participant Contact": {"display_name", "primary_phone", "email"},
			"Participant Health Alert": {"concise_summary", "response_instruction", "supporting_detail"},
		}.items():
			fields = set(frappe.get_meta(doctype).get_permitted_fieldnames(user=self.privacy))
			self.assertTrue({"participant", "status", "verification_status"}.issubset(fields))
			self.assertFalse(fields.intersection(restricted))

	def test_privacy_officer_cannot_read_contact_or_alert_attachments(self):
		for doctype in ("Participant Contact", "Participant Health Alert"):
			file_doc = frappe._dict(
				{
					"doctype": "File", "attached_to_doctype": doctype,
					"attached_to_name": "synthetic-metadata-record",
				}
			)
			self.assertFalse(permissions.has_evidence_file_permission(file_doc, "read", self.privacy))
		condition = permissions.get_evidence_file_permission_query_conditions(self.privacy)
		self.assertIn("Participant Contact", condition)
		self.assertIn("Participant Health Alert", condition)

def _test(predicate):
	def run(self): self.assertTrue(predicate())
	return run

for _name, _predicate in CASES:
	setattr(TestParticipantContactAlertPermissions, f"test_permission_{_name}", _test(_predicate))
