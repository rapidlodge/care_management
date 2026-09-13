# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_incident_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_incident_participants(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


MANAGER_FIELDS = frozenset({
	"assigned_staff",
	"manager_actions_and_comments",
	"manager_corrective_or_preventive_actions",
	"reportable_to_commission",
	"consequence_manager",
	"likelihood_manager",
	"incident_status",
	"is_this_likely_to_attract_media_attention",
	"action_and_notifications",
	"linked_incidents",
	"linked_date",
	"linked_comment",
})


class Incident(Document):
	def before_insert(self):
		if not self.incident_status:
			self.incident_status = "Open"
		self.reported_by = permissions.normalize_user()
		self.reported_on = now_datetime()

	def validate(self):
		self._validate_reporter_immutability()
		self._validate_actor()
		self._validate_medication_link()

	def on_trash(self):
		self._validate_not_referenced_by_medication_safeguards()

	def _validate_actor(self):
		actor = permissions.normalize_user()
		if not actor:
			raise frappe.PermissionError
		if actor == "Administrator" or permissions.has_any_role({"System Manager"}, user=actor):
			return
		permissions.require_participant_access(self.participant, user=actor, applicable_for=self.doctype)
		if permissions.has_any_role({"Care Manager"}, user=actor):
			return
		if permissions.has_any_role({"Support Worker"}, user=actor):
			self._validate_support_worker_fields(actor)
			if self.is_new() and self.incident_status == "Open":
				return
			if self.reported_by == actor and self.incident_status == "Open":
				return
		raise frappe.PermissionError

	def _validate_support_worker_fields(self, actor):
		if not self.is_new() and self.reported_by != actor:
			raise frappe.PermissionError
		if self.is_new():
			blocked_fields = [field for field in MANAGER_FIELDS if self.get(field) and field != "incident_status"]
			if blocked_fields:
				raise frappe.PermissionError
			return
		for fieldname in MANAGER_FIELDS:
			if self.has_value_changed(fieldname):
				raise frappe.PermissionError

	def _validate_medication_link(self):
		if not self.linked_medication_event:
			return
		if permissions.resolve_participant("Medication Administration Event", self.linked_medication_event) != self.participant:
			raise frappe.PermissionError

	def _validate_reporter_immutability(self):
		if self.is_new():
			return
		if self.has_value_changed("reported_by") or self.has_value_changed("reported_on"):
			frappe.throw("Incident reporter evidence cannot be changed after insertion.", frappe.ValidationError)

	def _validate_not_referenced_by_medication_safeguards(self):
		references = (
			("Medication Administration Event", {"incident": self.name, "docstatus": ["!=", 2]}),
			("Medication PRN Effectiveness Review", {"incident": self.name, "docstatus": ["!=", 2]}),
			("Participant Drug Count", {"discrepancy_incident": self.name, "docstatus": ["!=", 2]}),
			("Discarded Medication Item", {"discrepancy_incident": self.name}),
			("Controlled Medication Transaction", {"incident": self.name, "docstatus": ["!=", 2]}),
		)
		for doctype, filters in references:
			if frappe.db.exists(doctype, filters):
				frappe.throw("Incident is linked to medication safeguarding evidence and cannot be deleted.", frappe.ValidationError)
		drug_counts = frappe.get_all(
			"Participant Drug Count",
			filters={"discrepancy_incident": self.name, "docstatus": ["!=", 2]},
			pluck="name",
		)
		if drug_counts and frappe.db.exists(
			"Shift Medication Check",
			{"reconciliation": ["in", drug_counts], "docstatus": ["!=", 2]},
		):
			frappe.throw("Incident is linked to medication safeguarding evidence and cannot be deleted.", frappe.ValidationError)
