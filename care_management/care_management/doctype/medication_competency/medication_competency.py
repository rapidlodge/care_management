# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from care_management.care_management import permissions


class MedicationCompetency(Document):
	def validate(self):
		self._validate_worker()
		self._validate_dates()
		self._validate_unique_active_window()

	def on_trash(self):
		frappe.throw("Medication competency evidence cannot be deleted; use Inactive or Revoked status.", frappe.ValidationError)

	def _validate_worker(self):
		if not permissions.is_enabled_system_user(self.worker):
			frappe.throw("Medication competency requires an enabled System User.", frappe.ValidationError)
		if not permissions.has_any_role({"Support Worker"}, user=self.worker):
			frappe.throw("Medication competency requires a Support Worker.", frappe.ValidationError)

	def _validate_dates(self):
		if getdate(self.valid_from) > getdate(self.expiry_date):
			frappe.throw("Medication competency expiry must be on or after the start date.", frappe.ValidationError)
		if self.status == "Active" and getdate(self.expiry_date) < getdate(nowdate()):
			frappe.throw("Expired competency cannot remain Active.", frappe.ValidationError)

	def _validate_unique_active_window(self):
		if self.status != "Active" or not self.is_active:
			return
		for row in frappe.get_all(
			"Medication Competency",
			filters={
				"worker": self.worker,
				"competency_type": self.competency_type,
				"status": "Active",
				"is_active": 1,
			},
			fields=["name", "valid_from", "expiry_date"],
		):
			if row.name == self.name:
				continue
			if getdate(self.valid_from) <= getdate(row.expiry_date) and getdate(row.valid_from) <= getdate(self.expiry_date):
				frappe.throw("Overlapping active medication competency records are not allowed.", frappe.ValidationError)


def has_active_medication_competency(worker, competency_type="General Medication", on_date=None):
	worker = permissions.normalize_user(worker)
	if not worker:
		return False
	on_date = getdate(on_date or nowdate())
	for row in frappe.get_all(
		"Medication Competency",
		filters={
			"worker": worker,
			"competency_type": competency_type,
			"status": "Active",
			"is_active": 1,
		},
		fields=["valid_from", "expiry_date"],
	):
		if getdate(row.valid_from) <= on_date <= getdate(row.expiry_date):
			return True
	return False
