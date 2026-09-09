# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

from decimal import Decimal

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from care_management.care_management import permissions
from care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction import (
	latest_balance,
	lock_plan_item_row,
)


@frappe.whitelist()
def search_participant_drug_count_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_participant_drug_count_participants(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


class ParticipantDrugCount(Document):
	def before_insert(self):
		if permissions.has_any_role({"Support Worker"}) and not permissions.has_any_role({"Care Manager", "System Manager"}):
			self.observed_by = permissions.normalize_user()

	def validate(self):
		self._validate_actor()
		self._validate_plan_item()
		self._set_discrepancy()

	def before_submit(self):
		actor = permissions.normalize_user()
		if actor != "Administrator" and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
			raise frappe.PermissionError
		self._derive_reconciliation()
		if self.discrepancy_quantity and Decimal(str(self.discrepancy_quantity)) != Decimal("0"):
			if self.reconciliation_status != "Escalated" or not self.discrepancy_incident:
				frappe.throw("Drug count discrepancies require escalation and a linked Incident.", frappe.ValidationError)
		else:
			self.reconciliation_status = "Reconciled"
		self.reconciled_by = actor
		self.reconciled_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Submitted drug-count reconciliation evidence cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Submitted drug-count reconciliation evidence cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted drug-count reconciliation evidence cannot be deleted.", frappe.ValidationError)

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
			if self.is_new() and self.observed_by == actor:
				return
			stored = frappe.db.get_value(self.doctype, self.name, ["observed_by", "docstatus"], as_dict=True)
			if stored and stored.observed_by == actor and stored.docstatus == 0 and self.observed_by == actor:
				return
			raise frappe.PermissionError
		raise frappe.PermissionError

	def _set_discrepancy(self):
		if not self.medication_plan_item:
			frappe.throw("Drug-count reconciliation requires a medication plan item.", frappe.ValidationError)
		if self.observed_balance in (None, ""):
			frappe.throw("Drug-count reconciliation requires an observed balance.", frappe.ValidationError)
		lock_plan_item_row(self.medication_plan_item)
		self.expected_balance = str(latest_balance(self.participant, self.medication_plan_item))
		self._derive_reconciliation()

	def _derive_reconciliation(self):
		if self.observed_balance in (None, ""):
			return
		expected = Decimal(str(self.expected_balance or 0))
		observed = Decimal(str(self.observed_balance))
		self.discrepancy_quantity = str(observed - expected)
		if Decimal(str(self.discrepancy_quantity)) == Decimal("0"):
			self.reconciliation_status = "Reconciled"
		elif self.reconciliation_status == "Reconciled":
			frappe.throw("Discrepancy records cannot be labelled Reconciled.", frappe.ValidationError)
		if self.discrepancy_incident and permissions.resolve_participant("Incident", self.discrepancy_incident) != self.participant:
			raise frappe.PermissionError

	def _validate_plan_item(self):
		if not self.medication_plan_item:
			return
		plan_name = frappe.db.get_value("Medication Plan Item", self.medication_plan_item, "parent")
		if not plan_name:
			frappe.throw("Drug-count reconciliation requires an authoritative medication plan item.", frappe.ValidationError)
		if permissions.resolve_participant("Medication Administration Log", plan_name) != self.participant:
			raise frappe.PermissionError
