# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime

from care_management.care_management import permissions
from care_management.care_management.doctype.medication_competency.medication_competency import (
	has_active_medication_competency,
)
from care_management.care_management.doctype.medication_plan_item.medication_plan_item import (
	validate_active_medication_plan_item,
)


class MedicationAdministrationEvent(Document):
	def before_insert(self):
		self.docstatus = 0
		self.finalized_by = None
		self.finalized_on = None

	def validate(self):
		if self.is_new():
			self.docstatus = 0
			self.finalized_by = None
			self.finalized_on = None
		self._validate_authoritative_context()
		self._set_occurrence_key()
		self._validate_duplicate_occurrence()

	def before_submit(self):
		if not self.outcome:
			frappe.throw("Administration outcome is required before finalization.", frappe.ValidationError)
		self._validate_outcome_details()
		self._validate_worker_authority()
		self.finalized_by = permissions.normalize_user()
		self.finalized_on = now_datetime()

	def before_cancel(self):
		frappe.throw("Submitted medication administration evidence cannot be cancelled.", frappe.ValidationError)

	def before_update_after_submit(self):
		frappe.throw("Submitted medication administration evidence cannot be edited.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted medication administration evidence cannot be deleted.", frappe.ValidationError)

	def _plan_and_item(self):
		plan = frappe.get_doc("Medication Administration Log", self.medication_plan)
		if plan.participant != self.participant:
			frappe.throw("Medication event participant must match the selected plan.", frappe.PermissionError)
		if plan.plan_status != "Active":
			frappe.throw("Medication events require an active medication plan.", frappe.ValidationError)
		for row in plan.medication_items:
			if row.name == self.medication_plan_item:
				if not row.get("is_active", 1):
					frappe.throw("Medication events require an active plan item.", frappe.ValidationError)
				validate_active_medication_plan_item(row)
				return plan, row
		frappe.throw("Medication plan item must belong to the selected plan.", frappe.ValidationError)

	def _validate_authoritative_context(self):
		plan, item = self._plan_and_item()
		self._validate_linked_incident()
		self._validate_correction_closed()
		self._validate_authoritative_schedule(plan, item)
		self.prescribed_dose = item.prescribed_dose
		self.dose_unit = item.dose_unit
		self.route = item.route
		if self.support_task:
			task = frappe.get_doc("Support Task", self.support_task)
			task_participant = permissions.resolve_participant("Support Task", task.name)
			if task_participant != self.participant:
				frappe.throw("Support Task participant does not match the medication event.", frappe.PermissionError)
			if task.status != "Active":
				frappe.throw("Medication events require an active Support Task.", frappe.ValidationError)
			if task.source_doctype != "Medication Administration Log" or task.source_docname != self.medication_plan:
				frappe.throw("Support Task must belong to the medication plan context.", frappe.ValidationError)
			if task.source_row_id != self.medication_plan_item:
				frappe.throw("Support Task must belong to the medication plan item context.", frappe.ValidationError)
			self._validate_task_schedule(task, item)
		if self.execution_instance:
			execution = frappe.get_doc("Support Task Execution Instance", self.execution_instance)
			if not self.support_task or execution.support_task != self.support_task:
				frappe.throw("Execution instance must belong to the selected Support Task.", frappe.ValidationError)
			execution_participant = permissions.resolve_participant("Support Task Execution Instance", execution.name)
			if execution_participant != self.participant:
				frappe.throw("Execution instance participant does not match the medication event.", frappe.PermissionError)
			execution_dt = _execution_scheduled_datetime(execution)
			if not execution_dt:
				frappe.throw("Execution instance lacks an authoritative scheduled occurrence.", frappe.ValidationError)
			if get_datetime(self.scheduled_datetime) != execution_dt:
				frappe.throw("Medication event must match the execution scheduled occurrence.", frappe.ValidationError)
		if not self.actual_datetime:
			self.actual_datetime = now_datetime()

	def _validate_linked_incident(self):
		if not self.incident:
			return
		if permissions.resolve_participant("Incident", self.incident) != self.participant:
			raise frappe.PermissionError

	def _validate_correction_closed(self):
		if self.correction_source or self.correction_reason:
			frappe.throw("Medication correction workflow is not enabled in R3C.1.", frappe.ValidationError)

	def _validate_authoritative_schedule(self, plan, item):
		if not item.scheduled_time:
			frappe.throw("Medication plan item lacks an authoritative scheduled time.", frappe.ValidationError)
		scheduled = get_datetime(self.scheduled_datetime)
		scheduled_date = getdate(scheduled)
		if getdate(plan.effective_from) > scheduled_date:
			frappe.throw("Medication event is outside the medication plan effective period.", frappe.ValidationError)
		if plan.effective_to and scheduled_date > getdate(plan.effective_to):
			frappe.throw("Medication event is outside the medication plan effective period.", frappe.ValidationError)
		if item.frequency == "Selected Days" and not item.get(_weekday_field(scheduled_date)):
			frappe.throw("Medication event weekday is not selected on the plan item.", frappe.ValidationError)
		if item.frequency not in {"Daily", "Selected Days"}:
			frappe.throw("Unknown medication frequency is not safe for administration.", frappe.ValidationError)
		expected = get_datetime(f"{getdate(scheduled)} {item.scheduled_time}")
		if scheduled != expected:
			frappe.throw("Medication event scheduled time must match the authoritative plan item.", frappe.ValidationError)

	def _validate_task_schedule(self, task, item):
		scheduled = get_datetime(self.scheduled_datetime)
		scheduled_date = getdate(scheduled)
		for rule in task.schedule_rules:
			if get_datetime(f"{scheduled_date} {rule.scheduled_time}") != scheduled:
				continue
			if getdate(rule.start_date) > scheduled_date:
				continue
			if rule.end_date and scheduled_date > getdate(rule.end_date):
				continue
			if rule.recurrence_type == "Daily":
				return
			if rule.recurrence_type == "Selected Days" and rule.get(_weekday_field(scheduled_date)):
				return
		frappe.throw("Medication event must match an authoritative Support Task schedule.", frappe.ValidationError)

	def _set_occurrence_key(self):
		source = f"{self.medication_plan_item}|{get_datetime(self.scheduled_datetime).isoformat()}"
		self.occurrence_key = hashlib.sha256(source.encode("utf-8")).hexdigest()

	def _validate_duplicate_occurrence(self):
		filters = {
			"occurrence_key": self.occurrence_key,
			"docstatus": ["<", 2],
		}
		existing = frappe.get_all("Medication Administration Event", filters=filters, pluck="name", limit=1)
		if existing and existing[0] != self.name:
			frappe.throw("Duplicate medication administration evidence is not allowed.", frappe.ValidationError)

	def _validate_worker_authority(self):
		actor = permissions.normalize_user()
		worker = permissions.normalize_user(self.worker)
		if not actor:
			raise frappe.PermissionError
		if not worker:
			raise frappe.PermissionError
		if not permissions.is_enabled_system_user(worker):
			raise frappe.PermissionError
		if not permissions.has_any_role({"Support Worker"}, user=worker):
			raise frappe.PermissionError
		if not permissions.has_participant_access(
			self.participant,
			user=worker,
			applicable_for="Medication Administration Event",
		):
			raise frappe.PermissionError
		if self.support_task and not permissions.has_task_assignment(self.support_task, user=worker):
			raise frappe.PermissionError
		if not has_active_medication_competency(worker, "General Medication", getdate(self.scheduled_datetime)):
			raise frappe.PermissionError
		if actor in {"Administrator"} or permissions.has_any_role({"System Manager"}, user=actor):
			if not self.administrative_override_reason:
				raise frappe.PermissionError
			return
		if permissions.has_any_role({"Care Manager"}, user=actor):
			raise frappe.PermissionError
		if actor == worker:
			return
		raise frappe.PermissionError

	def _validate_outcome_details(self):
		if self.outcome == "Administered" and not self.administered_dose:
			frappe.throw("Administered medication events require an administered dose.", frappe.ValidationError)
		if self.outcome == "Administered" and self.administered_dose != self.prescribed_dose and not self.variance_reason:
			frappe.throw("Dose variance requires a variance reason.", frappe.ValidationError)
		if self.outcome in {"Refused", "Missed", "Withheld", "Not Available", "Error"} and not self.variance_reason:
			frappe.throw("Non-administered outcomes require a variance reason.", frappe.ValidationError)


def _weekday_field(date_value):
	return ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[getdate(date_value).weekday()]


def _execution_scheduled_datetime(execution):
	if execution.get("scheduled_datetime"):
		return get_datetime(execution.scheduled_datetime)
	if execution.get("scheduled_date") and execution.get("scheduled_time"):
		return get_datetime(f"{execution.scheduled_date} {execution.scheduled_time}")
	return None
