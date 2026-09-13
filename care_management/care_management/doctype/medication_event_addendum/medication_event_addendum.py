# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_event_addendum_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_medication_event_addendum_participants(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_event_addendum_events(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_medication_event_addendum_events(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


class MedicationEventAddendum(Document):
	def before_insert(self):
		self._derive_event_context()
		self._validate_author_permissions()
		self.created_by = permissions.normalize_user()
		self.created_on = now_datetime()

	def validate(self):
		self._derive_event_context()
		self._validate_author_permissions()
		self._validate_required_reason()
		self._validate_single_active_addendum()

	def before_submit(self):
		self._lock_original_event()
		self._derive_event_context()
		self._validate_required_reason()
		self._validate_manager_review()
		self._validate_single_active_addendum()
		self.reviewed_by = permissions.normalize_user()
		self.reviewed_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Submitted medication event addenda cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Submitted medication event addenda cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted medication event addenda cannot be deleted.", frappe.ValidationError)

	def _derive_event_context(self):
		if not self.medication_event:
			frappe.throw("Medication Event Addendum requires a submitted medication event.", frappe.ValidationError)
		event = frappe.get_doc("Medication Administration Event", self.medication_event)
		if event.docstatus != 1:
			frappe.throw("Medication Event Addendum requires a submitted medication event.", frappe.ValidationError)

		derived = {
			"participant": event.participant,
			"medication_plan": event.medication_plan,
			"medication_plan_item": event.medication_plan_item,
			"event_worker": event.worker,
			"event_scheduled_datetime": event.scheduled_datetime,
			"event_actual_datetime": event.actual_datetime,
			"original_outcome": event.outcome,
			"original_administered_dose": event.administered_dose,
			"original_dose_unit": event.dose_unit,
		}
		for fieldname, value in derived.items():
			current = self.get(fieldname)
			if current and str(current) != str(value):
				raise frappe.PermissionError
			self.set(fieldname, value)

	def _validate_author_permissions(self):
		actor = permissions.normalize_user()
		if not actor:
			raise frappe.PermissionError
		if self.created_by and self.created_by != actor and self.is_new():
			raise frappe.PermissionError
		if actor == "Administrator" or permissions.has_any_role({"System Manager"}, user=actor):
			return
		permissions.require_participant_access(
			self.participant,
			user=actor,
			applicable_for=self.doctype,
		)
		if permissions.has_any_role({"Care Manager"}, user=actor):
			return
		if permissions.has_any_role({"Support Worker"}, user=actor) and self.event_worker == actor:
			return
		raise frappe.PermissionError

	def _validate_required_reason(self):
		if not self.amendment_reason or not str(self.amendment_reason).strip():
			frappe.throw("Medication Event Addendum requires an amendment reason.", frappe.ValidationError)
		if not self.correction_explanation or not str(self.correction_explanation).strip():
			frappe.throw("Medication Event Addendum requires correction explanation.", frappe.ValidationError)

	def _validate_manager_review(self):
		actor = permissions.normalize_user()
		if self.reviewed_by and self.reviewed_by != actor:
			raise frappe.PermissionError
		if actor != "Administrator" and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
			raise frappe.PermissionError
		if not permissions.is_administrator(actor) and not permissions.is_system_manager(actor):
			permissions.require_participant_access(
				self.participant,
				user=actor,
				applicable_for=self.doctype,
			)
		if self.review_decision not in {"Approved", "Rejected"}:
			frappe.throw("Medication Event Addendum requires manager review decision.", frappe.ValidationError)
		if not self.review_comments or not str(self.review_comments).strip():
			frappe.throw("Medication Event Addendum requires manager review comments.", frappe.ValidationError)

	def _validate_single_active_addendum(self):
		if not self.medication_event:
			return
		existing = frappe.db.exists(
			self.doctype,
			{
				"medication_event": self.medication_event,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw("Only one active medication event addendum is allowed per medication event.", frappe.ValidationError)

	def _lock_original_event(self):
		frappe.db.sql(
			"select name from `tabMedication Administration Event` where name = %s for update",
			(self.medication_event,),
		)
