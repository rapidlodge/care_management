from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime, nowdate

from care_management.care_management import permissions
from care_management.care_management.doctype.medication_event_addendum import medication_event_addendum
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)


class TestMedicationEventAddendum(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R3E A", "6234567890")
		self.participant_b = ensure_r2c1_participant("R3E B", "7234567890")
		self.worker = ensure_r2c1_user("R3E Worker", ["Support Worker"])
		self.worker_b = ensure_r2c1_user("R3E Worker B", ["Support Worker"])
		self.care_manager = ensure_r2c1_user("R3E Care Manager", ["Care Manager"])
		self.care_manager_b = ensure_r2c1_user("R3E Care Manager B", ["Care Manager"])
		self.support_coordinator = ensure_r2c1_user("R3E Support Coordinator", ["Support Coordinator"])
		self.system_manager = ensure_r2c1_user("R3E System Manager", ["System Manager"])
		for user, participant in (
			(self.worker, self.participant_a),
			(self.care_manager, self.participant_a),
			(self.support_coordinator, self.participant_a),
			(self.worker_b, self.participant_b),
			(self.care_manager_b, self.participant_b),
		):
			ensure_r2c1_user_permission(user, participant, applicable_for="Medication Administration Event")
			ensure_r2c1_user_permission(user, participant, applicable_for="Medication Event Addendum")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_plan(self, participant=None, worker=None):
		frappe.set_user("Administrator")
		participant = participant or self.participant_a
		worker = worker or self.worker
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": participant,
				"week_commencing": nowdate(),
				"plan_status": "Draft",
				"plan_version": 1,
				"effective_from": nowdate(),
				"review_date": add_days(nowdate(), 30),
				"purpose_evidence_status": "Recorded",
				"change_reason": "R3E activation",
				"medication_items": [
					{
						"medication_name": "R3E Paracetamol",
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
		support_plan = ensure_r2c1_support_plan(participant, f"R3E {participant}")
		task = frappe.get_doc(
			{
				"doctype": "Support Task",
				"support_plan": support_plan,
				"task_name": f"R3E Medication Task {frappe.generate_hash(length=8)}",
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
		ensure_r2c1_task_assignment(task.name, worker)
		return plan, task.name

	def grant_competency(self, worker=None):
		frappe.set_user("Administrator")
		worker = worker or self.worker
		existing = frappe.db.get_value(
			"Medication Competency",
			{
				"worker": worker,
				"competency_type": "General Medication",
				"status": "Active",
			},
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
				"expiry_date": nowdate(),
				"assessed_by": self.care_manager,
				"assessed_on": nowdate(),
			}
		).insert(ignore_permissions=True).name

	def submitted_event(self, participant=None, worker=None):
		frappe.set_user("Administrator")
		participant = participant or self.participant_a
		worker = worker or self.worker
		self.grant_competency(worker)
		plan, task = self.make_plan(participant=participant, worker=worker)
		event = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": participant,
				"medication_plan": plan.name,
				"medication_plan_item": plan.medication_items[0].name,
				"support_task": task,
				"scheduled_datetime": f"{nowdate()} 08:00:00",
				"actual_datetime": f"{nowdate()} 08:01:00",
				"worker": worker,
				"outcome": "Administered",
				"administered_dose": "10",
			}
		)
		frappe.set_user(worker)
		event.insert()
		event.submit()
		frappe.set_user("Administrator")
		return event.name

	def draft_addendum(self, event_name=None, user=None, **overrides):
		event_name = event_name or self.submitted_event()
		user = user or self.worker
		values = {
			"doctype": "Medication Event Addendum",
			"medication_event": event_name,
			"amendment_reason": "Incorrect administration note",
			"correction_explanation": "Dose note clarified without changing original event.",
		}
		values.update(overrides)
		frappe.set_user(user)
		return frappe.get_doc(values)

	def test_permitted_worker_can_create_draft_from_own_submitted_event(self):
		doc = self.draft_addendum()
		doc.insert()
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.participant, self.participant_a)
		self.assertEqual(doc.created_by, self.worker)
		self.assertTrue(doc.created_on)

	def test_unauthorized_worker_and_cross_participant_access_are_denied(self):
		event = self.submitted_event()
		with self.assertRaises(frappe.PermissionError):
			self.draft_addendum(event_name=event, user=self.worker_b).insert()
		with self.assertRaises(frappe.PermissionError):
			self.draft_addendum(event_name=event, user=self.worker, participant=self.participant_b).insert()

	def test_manager_approval_and_amendment_reason_are_required(self):
		doc = self.draft_addendum().insert()
		frappe.set_user(self.care_manager)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		doc.amendment_reason = ""
		doc.review_decision = "Approved"
		doc.review_comments = "Reviewed"
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_care_manager_can_approve_and_finalize_for_granted_participant(self):
		doc = self.draft_addendum().insert()
		frappe.set_user(self.care_manager)
		doc.review_decision = "Approved"
		doc.review_comments = "Clinically reviewed and accepted."
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.reviewed_by, self.care_manager)
		self.assertTrue(doc.reviewed_on)
		self.assertEqual(frappe.get_doc("Medication Administration Event", doc.medication_event).docstatus, 1)

	def test_actor_and_reviewer_spoofing_are_denied(self):
		event = self.submitted_event()
		doc = self.draft_addendum(event_name=event, created_by=self.worker_b)
		with self.assertRaises(frappe.PermissionError):
			doc.insert()
		doc = self.draft_addendum(event_name=event).insert()
		frappe.set_user(self.care_manager)
		doc.reviewed_by = self.system_manager
		doc.review_decision = "Approved"
		doc.review_comments = "Reviewed"
		with self.assertRaises(frappe.PermissionError):
			doc.submit()

	def test_finalized_addendum_is_immutable_and_cannot_be_cancelled_or_deleted(self):
		doc = self.draft_addendum().insert()
		frappe.set_user(self.care_manager)
		doc.review_decision = "Approved"
		doc.review_comments = "Reviewed"
		doc.submit()
		doc.correction_explanation = "changed"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			doc.cancel()
		doc = frappe.get_doc("Medication Event Addendum", doc.name)
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			doc.delete()

	def test_document_and_list_permissions_are_participant_scoped(self):
		own = self.draft_addendum().insert()
		other_event = self.submitted_event(participant=self.participant_b, worker=self.worker_b)
		other = self.draft_addendum(event_name=other_event, user=self.worker_b).insert()
		frappe.set_user(self.worker)
		self.assertTrue(frappe.has_permission("Medication Event Addendum", "read", doc=own, user=self.worker))
		self.assertFalse(frappe.has_permission("Medication Event Addendum", "read", doc=other, user=self.worker))
		names = {row.name for row in frappe.get_list("Medication Event Addendum", fields=["name"])}
		self.assertIn(own.name, names)
		self.assertNotIn(other.name, names)

	def test_attachment_boundary_follows_addendum_document_permission(self):
		doc = self.draft_addendum().insert()
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "r3e-addendum-evidence.txt",
				"attached_to_doctype": "Medication Event Addendum",
				"attached_to_name": doc.name,
				"content": "synthetic addendum evidence",
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self.assertTrue(frappe.has_permission("Medication Event Addendum", "read", doc=doc, user=self.worker))
		self.assertFalse(frappe.has_permission("Medication Event Addendum", "read", doc=doc, user=self.worker_b))
		self.assertTrue(frappe.has_permission("File", "read", doc=file_doc, user=self.worker))
		self.assertFalse(frappe.has_permission("File", "read", doc=file_doc, user=self.worker_b))

	def test_duplicate_active_addendum_is_denied_for_same_event(self):
		event = self.submitted_event()
		self.draft_addendum(event_name=event).insert()
		with self.assertRaises(frappe.ValidationError):
			self.draft_addendum(event_name=event).insert()

	def test_provenance_fields_are_immutable_after_insert_for_all_privileged_roles(self):
		doc = self.draft_addendum(event_name=self.submitted_event()).insert()
		other_event = self.submitted_event(participant=self.participant_b, worker=self.worker_b)
		other_event_doc = frappe.get_doc("Medication Administration Event", other_event)
		for user in (self.worker, self.care_manager, self.system_manager):
			for fieldname, replacement in (
				("medication_event", other_event),
				("participant", self.participant_b),
				("medication_plan", other_event_doc.medication_plan),
				("medication_plan_item", other_event_doc.medication_plan_item),
				("event_worker", self.worker_b),
				("event_scheduled_datetime", f"{nowdate()} 09:00:00"),
				("event_actual_datetime", f"{nowdate()} 09:01:00"),
				("original_outcome", "Missed"),
				("original_administered_dose", "999"),
				("original_dose_unit", "ml"),
				("created_by", self.worker_b),
				("created_on", now_datetime()),
			):
				reloaded = frappe.get_doc("Medication Event Addendum", doc.name)
				frappe.set_user(user)
				reloaded.set(fieldname, replacement)
				with self.assertRaises(frappe.PermissionError):
					reloaded.save()

	def test_support_worker_cannot_craft_or_modify_manager_review_fields(self):
		event = self.submitted_event()
		for overrides in (
			{"review_decision": "Approved"},
			{"review_comments": "worker review"},
			{"reviewed_by": self.worker},
			{"reviewed_on": now_datetime()},
		):
			with self.assertRaises(frappe.PermissionError):
				self.draft_addendum(event_name=event, **overrides).insert(ignore_permissions=True)

		doc = self.draft_addendum(event_name=event).insert()
		self.assertEqual(doc.review_decision, "Pending")
		self.assertFalse(doc.review_comments)
		self.assertFalse(doc.reviewed_by)
		self.assertFalse(doc.reviewed_on)

		frappe.set_user(self.worker)
		doc.review_comments = "worker review"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		stored = frappe.get_doc("Medication Event Addendum", doc.name)
		self.assertEqual(stored.review_decision, "Pending")
		self.assertFalse(stored.review_comments)
		self.assertFalse(stored.reviewed_by)
		self.assertFalse(stored.reviewed_on)

	def test_manager_review_is_server_stamped_and_spoofed_review_metadata_is_denied(self):
		doc = self.draft_addendum().insert()
		frappe.set_user(self.care_manager)
		doc.review_decision = "Rejected"
		doc.review_comments = "Evidence needs replacement."
		doc.reviewed_by = self.system_manager
		with self.assertRaises(frappe.PermissionError):
			doc.submit()

		doc = frappe.get_doc("Medication Event Addendum", doc.name)
		frappe.set_user(self.care_manager)
		doc.review_decision = "Rejected"
		doc.review_comments = "Evidence needs replacement."
		doc.reviewed_on = now_datetime()
		with self.assertRaises(frappe.PermissionError):
			doc.submit()

		doc = frappe.get_doc("Medication Event Addendum", doc.name)
		frappe.set_user(self.care_manager)
		doc.review_decision = "Rejected"
		doc.review_comments = "Evidence needs replacement."
		doc.submit()
		self.assertEqual(doc.reviewed_by, self.care_manager)
		self.assertTrue(doc.reviewed_on)

	def test_rejected_addendum_allows_append_only_linked_replacement(self):
		event = self.submitted_event()
		rejected = self.draft_addendum(event_name=event).insert()
		frappe.set_user(self.care_manager)
		rejected.review_decision = "Rejected"
		rejected.review_comments = "Needs more precise explanation."
		rejected.submit()

		replacement = self.draft_addendum(event_name=event).insert()
		self.assertEqual(replacement.previous_addendum, rejected.name)
		self.assertEqual(replacement.sequence_number, 2)

		rejected = frappe.get_doc("Medication Event Addendum", rejected.name)
		rejected.review_comments = "rewrite rejected evidence"
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			rejected.save()

	def test_creation_locks_authoritative_event_before_duplicate_check(self):
		event = self.submitted_event()
		order = []

		def record_lock(doc):
			order.append("lock")

		def record_duplicate_check(doc):
			order.append("duplicate")

		with patch.object(
			medication_event_addendum.MedicationEventAddendum,
			"_lock_original_event",
			record_lock,
		), patch.object(
			medication_event_addendum.MedicationEventAddendum,
			"_validate_single_active_addendum",
			record_duplicate_check,
		):
			self.draft_addendum(event_name=event).insert()

		self.assertIn("duplicate", order)
		self.assertLess(order.index("lock"), order.index("duplicate"))

	def test_create_addendum_ui_authority_helper_is_event_specific(self):
		own_event = self.submitted_event()
		other_event = self.submitted_event(participant=self.participant_b, worker=self.worker_b)
		self.assertTrue(medication_event_addendum._can_create_medication_event_addendum(own_event, self.worker))
		self.assertFalse(medication_event_addendum._can_create_medication_event_addendum(other_event, self.worker))
		self.assertFalse(
			medication_event_addendum._can_create_medication_event_addendum(own_event, self.support_coordinator)
		)
		self.assertTrue(
			medication_event_addendum._can_create_medication_event_addendum(own_event, self.care_manager)
		)
		self.assertTrue(
			medication_event_addendum._can_create_medication_event_addendum(own_event, self.system_manager)
		)

	def test_internal_addendum_search_helpers_are_not_public_api(self):
		self.assertNotIn(permissions.search_medication_event_addendum_participants, frappe.whitelisted)
		self.assertNotIn(permissions.search_medication_event_addendum_events, frappe.whitelisted)
		self.assertIn(medication_event_addendum.search_medication_event_addendum_participants, frappe.whitelisted)
		self.assertIn(medication_event_addendum.search_medication_event_addendum_events, frappe.whitelisted)
