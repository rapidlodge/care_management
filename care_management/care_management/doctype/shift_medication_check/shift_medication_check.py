# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions


class ShiftMedicationCheck(Document):
	def before_insert(self):
		if permissions.has_any_role({"Support Worker"}) and not permissions.has_any_role({"Care Manager", "System Manager"}):
			self.checked_by = permissions.normalize_user()

	def validate(self):
		self._validate_actor()
		self._validate_reconciliation()

	def before_submit(self):
		actor = permissions.normalize_user()
		if actor != "Administrator" and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
			raise frappe.PermissionError
		self.finalized_by = actor
		self.finalized_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Finalized shift medication checks cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Finalized shift medication checks cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Finalized shift medication checks cannot be deleted.", frappe.ValidationError)

	def _validate_actor(self):
		actor = permissions.normalize_user()
		if not actor:
			raise frappe.PermissionError
		if actor == "Administrator" or permissions.has_any_role({"System Manager"}, user=actor):
			return
		permissions.require_participant_access(self.participant, user=actor, applicable_for=self.doctype)
		if permissions.has_any_role({"Care Manager"}, user=actor):
			return
		if self.docstatus == 0 and permissions.has_any_role({"Support Worker"}, user=actor):
			if self.is_new() and self.checked_by == actor:
				return
			stored = frappe.db.get_value(self.doctype, self.name, ["checked_by", "docstatus"], as_dict=True)
			if stored and stored.checked_by == actor and stored.docstatus == 0 and self.checked_by == actor:
				return
			raise frappe.PermissionError
		raise frappe.PermissionError

	def _validate_reconciliation(self):
		if not self.reconciliation:
			frappe.throw("Shift medication check finalization requires an exact drug-count reconciliation.", frappe.ValidationError)
		reconciliation = frappe.db.get_value(
			"Participant Drug Count",
			self.reconciliation,
			["participant", "docstatus", "reconciliation_status"],
			as_dict=True,
		)
		if not reconciliation:
			frappe.throw("Shift medication check requires an existing drug-count reconciliation.", frappe.ValidationError)
		if reconciliation.participant != self.participant:
			raise frappe.PermissionError
		if reconciliation.docstatus != 1 or reconciliation.reconciliation_status != "Reconciled":
			frappe.throw("Shift medication check requires a submitted exact drug-count reconciliation.", frappe.ValidationError)
