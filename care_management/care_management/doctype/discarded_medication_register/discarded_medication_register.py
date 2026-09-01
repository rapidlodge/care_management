# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions
from care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction import create_source_transaction


class DiscardedMedicationRegister(Document):
	def before_insert(self):
		if permissions.has_any_role({"Support Worker"}) and not permissions.has_any_role({"Care Manager", "System Manager"}):
			self.prepared_by = permissions.normalize_user()

	def validate(self):
		self._validate_actor()
		for row in self.discarded_items:
			self._validate_row(row)

	def before_submit(self):
		actor = permissions.normalize_user()
		if actor != "Administrator" and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
			raise frappe.PermissionError
		for row in self.discarded_items:
			if self._row_is_controlled(row):
				type_name = "Return to Pharmacy" if row.get("disposal_type") == "Return to Pharmacy" else "Disposal"
				txn = create_source_transaction(self._row_source(row), type_name, row.quantity, row.witness, incident=row.discrepancy_incident)
				row.controlled_transaction = txn.name
		if self.disposal_status != "Escalated":
			self.disposal_status = "Finalized"
		self.finalized_by = actor
		self.finalized_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Submitted discarded-medication evidence cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Submitted discarded-medication evidence cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted discarded-medication evidence cannot be deleted.", frappe.ValidationError)

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
			if self.is_new() and self.prepared_by == actor:
				return
			stored = frappe.db.get_value(self.doctype, self.name, ["prepared_by", "docstatus"], as_dict=True)
			if stored and stored.prepared_by == actor and stored.docstatus == 0 and self.prepared_by == actor:
				return
			raise frappe.PermissionError
		raise frappe.PermissionError

	def _validate_row(self, row):
		if not row.medication_plan_item or not row.quantity or not row.dose_unit:
			frappe.throw("Discarded medication requires plan item, quantity and unit.", frappe.ValidationError)
		plan_name = frappe.db.get_value("Medication Plan Item", row.medication_plan_item, "parent")
		if not plan_name:
			frappe.throw("Discarded medication requires an authoritative medication plan item.", frappe.ValidationError)
		if permissions.resolve_participant("Medication Administration Log", plan_name) != self.participant:
			raise frappe.PermissionError
		plan_item = frappe.db.get_value(
			"Medication Plan Item",
			row.medication_plan_item,
			["dose_unit", "is_controlled_drug"],
			as_dict=True,
		)
		if plan_item.dose_unit != row.dose_unit:
			frappe.throw("Discarded medication unit must match the medication plan item.", frappe.ValidationError)
		row.is_controlled_drug = 1 if plan_item.is_controlled_drug else 0
		if self._row_is_controlled(row):
			self._validate_controlled_row_authority(row)
		if bool(row.discrepancy_incident) != (self.disposal_status == "Escalated" or row.get("incident_reported") == "Yes"):
			frappe.throw("Discarded medication escalation and incident evidence must agree.", frappe.ValidationError)
		if row.discrepancy_incident and permissions.resolve_participant("Incident", row.discrepancy_incident) != self.participant:
			raise frappe.PermissionError

	def _row_is_controlled(self, row):
		return bool(row.get("is_controlled_drug"))

	def _validate_controlled_row_authority(self, row):
		if not row.witness:
			frappe.throw("Controlled medication disposal requires a witness.", frappe.ValidationError)
		staff_user = permissions.normalize_user(row.staff_disposing_medication)
		witness_user = permissions.normalize_user(row.witness)
		if not staff_user or not witness_user or staff_user == witness_user:
			raise frappe.PermissionError
		for user in (staff_user, witness_user):
			if not permissions.is_enabled_system_user(user):
				raise frappe.PermissionError
			if not permissions.has_any_role({"Support Worker", "Care Manager", "System Manager"}, user=user):
				raise frappe.PermissionError
			if user != "Administrator" and not permissions.has_participant_access(
				self.participant,
				user=user,
				administrative=permissions.is_system_manager(user),
				applicable_for=self.doctype,
			):
				raise frappe.PermissionError

	def _row_source(self, row):
		return frappe._dict(
			{
				"doctype": self.doctype,
				"name": self.name,
				"participant": self.participant,
				"medication_plan": frappe.db.get_value("Medication Plan Item", row.medication_plan_item, "parent"),
				"medication_plan_item": row.medication_plan_item,
				"source_action": f"{row.name or row.idx}:disposal",
				"operational_actor": permissions.normalize_user(row.staff_disposing_medication),
				"actual_datetime": now_datetime(),
				"dose_unit": row.dose_unit,
			}
		)
