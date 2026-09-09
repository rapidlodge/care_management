# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_prn_review_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_medication_prn_review_participants(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_prn_review_events(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_medication_prn_review_events(doctype, txt, searchfield, start, page_len, filters=filters)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_prn_review_plans(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_medication_prn_review_plans(doctype, txt, searchfield, start, page_len, filters=filters)


class MedicationPRNEffectivenessReview(Document):
	def validate(self):
		self._validate_event_context()
		self._validate_actor_permissions()
		self._validate_incident()

	def before_submit(self):
		actor = permissions.normalize_user()
		if actor != "Administrator" and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
			raise frappe.PermissionError
		self._lock_reviewed_event()
		self._validate_single_submitted_review()
		self.finalized_by = actor
		self.finalized_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Submitted PRN effectiveness reviews cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Submitted PRN effectiveness reviews cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted PRN effectiveness reviews cannot be deleted.", frappe.ValidationError)

	def _validate_event_context(self):
		event = frappe.get_doc("Medication Administration Event", self.medication_event)
		if event.docstatus != 1 or event.outcome != "Administered" or not event.is_prn_snapshot:
			frappe.throw("PRN effectiveness review requires a submitted administered PRN event.", frappe.ValidationError)
		if event.participant != self.participant:
			raise frappe.PermissionError
		self.medication_plan = event.medication_plan
		self.medication_plan_item = event.medication_plan_item
		self.administering_worker = event.worker
		self.review_due_at = event.prn_review_due_at

	def _validate_actor_permissions(self):
		actor = permissions.normalize_user()
		if not actor:
			raise frappe.PermissionError
		if actor == self.administering_worker and self.docstatus == 0:
			permissions.require_participant_access(
				self.participant, user=actor, applicable_for="Medication PRN Effectiveness Review"
			)
			return
		if actor == "Administrator" or permissions.has_any_role({"System Manager"}, user=actor):
			return
		if permissions.has_any_role({"Care Manager"}, user=actor):
			permissions.require_participant_access(
				self.participant, user=actor, applicable_for="Medication PRN Effectiveness Review"
			)
			return
		raise frappe.PermissionError

	def _validate_incident(self):
		if self.effectiveness_outcome != "Adverse Reaction":
			return
		if not self.incident:
			frappe.throw("Adverse Reaction review requires a linked Incident.", frappe.ValidationError)
		if permissions.resolve_participant("Incident", self.incident) != self.participant:
			raise frappe.PermissionError
		if frappe.db.get_value("Incident", self.incident, "incident_type") != "Adverse Medication Reaction":
			frappe.throw("Adverse Reaction review requires an Adverse Medication Reaction Incident.", frappe.ValidationError)

	def _validate_single_submitted_review(self):
		self._validate_event_context()
		existing = frappe.db.exists(
			self.doctype,
			{
				"medication_event": self.medication_event,
				"participant": self.participant,
				"docstatus": 1,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw("Only one submitted PRN effectiveness review is allowed per medication event.", frappe.ValidationError)

	def _lock_reviewed_event(self):
		if not self.medication_event:
			frappe.throw("PRN effectiveness review requires a medication event.", frappe.ValidationError)
		frappe.db.sql(
			"select name from `tabMedication Administration Event` where name = %s for update",
			(self.medication_event,),
		)
