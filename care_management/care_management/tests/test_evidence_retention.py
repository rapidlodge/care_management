import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime, nowdate

from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)


class TestEvidenceRetention(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R3F A", "8234567890")
		self.participant_b = ensure_r2c1_participant("R3F B", "9234567890")
		self.worker = ensure_r2c1_user("R3F Worker", ["Support Worker"])
		self.worker_b = ensure_r2c1_user("R3F Worker B", ["Support Worker"])
		self.care_manager = ensure_r2c1_user("R3F Care Manager", ["Care Manager"])
		for doctype in (
			"Medication Administration Event",
			"Medication Event Addendum",
			"Medication Competency",
		):
			ensure_r2c1_user_permission(self.worker, self.participant_a, applicable_for=doctype)
			ensure_r2c1_user_permission(self.care_manager, self.participant_a, applicable_for=doctype)
			ensure_r2c1_user_permission(self.worker_b, self.participant_b, applicable_for=doctype)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def _grant_competency(self, worker=None):
		worker = worker or self.worker
		existing = frappe.db.get_value(
			"Medication Competency",
			{"worker": worker, "competency_type": "General Medication", "status": "Active"},
			"name",
		)
		if existing:
			return existing
		return frappe.get_doc(
			{
				"doctype": "Medication Competency",
				"worker": worker,
				"competency_type": "General Medication",
				"status": "Active",
				"valid_from": nowdate(),
				"expiry_date": add_days(nowdate(), 30),
				"assessed_by": self.care_manager,
				"assessed_on": nowdate(),
			}
		).insert(ignore_permissions=True).name

	def _active_plan_and_task(self):
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": nowdate(),
				"plan_status": "Draft",
				"plan_version": 1,
				"effective_from": nowdate(),
				"review_date": add_days(nowdate(), 30),
				"purpose_evidence_status": "Recorded",
				"change_reason": "R3F activation",
				"medication_items": [
					{
						"medication_name": "R3F Paracetamol",
						"dosage": "10 mg",
						"prescribed_dose": "10",
						"dose_unit": "mg",
						"route": "Oral",
						"time_slot": "8 AM",
						"medication_form": "Tablet",
						"strength": "10 mg",
						"frequency": "Daily",
						"scheduled_time": "08:00:00",
						"indication": "Routine support",
						"is_active": 1,
						"monday": 1,
						"tuesday": 1,
						"wednesday": 1,
						"thursday": 1,
						"friday": 1,
						"saturday": 1,
						"sunday": 1,
						"requires_competency": 1,
						"is_prn": 0,
						"is_controlled_drug": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Active"
		plan.save(ignore_permissions=True)
		support_plan = ensure_r2c1_support_plan(self.participant_a, "R3F A")
		task = frappe.get_doc(
			{
				"doctype": "Support Task",
				"support_plan": support_plan,
				"task_name": f"R3F Medication Task {frappe.generate_hash(length=8)}",
				"task_category": "Medication",
				"status": "Active",
				"clinical_priority": "Mandatory",
				"staff_count_required": 1,
				"source_doctype": "Medication Administration Log",
				"source_docname": plan.name,
				"source_row_id": plan.medication_items[0].name,
				"schedule_rules": [
					{
						"scheduled_time": "08:00:00",
						"recurrence_type": "Daily",
						"start_date": nowdate(),
						"is_floating": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		ensure_r2c1_task_assignment(task.name, self.worker)
		return plan, task.name

	def _submitted_event(self):
		self._grant_competency()
		plan, task = self._active_plan_and_task()
		event = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": self.participant_a,
				"medication_plan": plan.name,
				"medication_plan_item": plan.medication_items[0].name,
				"support_task": task,
				"scheduled_datetime": f"{nowdate()} 08:00:00",
				"actual_datetime": f"{nowdate()} 08:01:00",
				"worker": self.worker,
				"outcome": "Administered",
				"administered_dose": "10",
			}
		)
		frappe.set_user(self.worker)
		event.insert()
		event.submit()
		frappe.set_user("Administrator")
		return event

	def _submitted_addendum(self, event=None):
		event = event or self._submitted_event()
		frappe.set_user(self.worker)
		addendum = frappe.get_doc(
			{
				"doctype": "Medication Event Addendum",
				"medication_event": event.name,
				"amendment_reason": "R3F evidence clarification",
				"correction_explanation": "Attachment-retention test addendum.",
			}
		).insert()
		frappe.set_user(self.care_manager)
		addendum.review_decision = "Approved"
		addendum.review_comments = "R3F reviewed."
		addendum.submit()
		frappe.set_user("Administrator")
		return addendum

	def _file_for(self, doctype, name):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"r3f-{frappe.generate_hash(length=8)}.txt",
				"content": "R3F synthetic attachment evidence",
				"attached_to_doctype": doctype,
				"attached_to_name": name,
			}
		).insert(ignore_permissions=True)

	def test_submitted_evidence_attachment_cannot_be_deleted_detached_or_repointed(self):
		event = self._submitted_event()
		file_doc = self._file_for(event.doctype, event.name)

		with self.assertRaises(frappe.ValidationError):
			file_doc.delete(ignore_permissions=True)

		detached = self._file_for(event.doctype, event.name)
		detached.attached_to_name = None
		with self.assertRaises(frappe.ValidationError):
			detached.save(ignore_permissions=True)

		repointed = self._file_for(event.doctype, event.name)
		repointed.attached_to_doctype = "Medication Event Addendum"
		repointed.attached_to_name = self._submitted_addendum(event).name
		with self.assertRaises(frappe.ValidationError):
			repointed.save(ignore_permissions=True)

	def test_draft_evidence_attachment_cleanup_remains_possible(self):
		event = self._submitted_event()
		frappe.set_user(self.worker)
		addendum = frappe.get_doc(
			{
				"doctype": "Medication Event Addendum",
				"medication_event": event.name,
				"amendment_reason": "R3F draft cleanup",
				"correction_explanation": "Draft attachment can still be cleaned up.",
			}
		).insert()
		frappe.set_user("Administrator")
		file_doc = self._file_for(addendum.doctype, addendum.name)
		file_doc.delete(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("File", file_doc.name))

	def test_attachment_read_inherits_participant_boundary(self):
		addendum = self._submitted_addendum()
		file_doc = self._file_for(addendum.doctype, addendum.name)
		frappe.set_user(self.worker)
		self.assertTrue(frappe.has_permission("File", "read", doc=file_doc, user=self.worker))
		self.assertFalse(frappe.has_permission("File", "read", doc=file_doc, user=self.worker_b))
