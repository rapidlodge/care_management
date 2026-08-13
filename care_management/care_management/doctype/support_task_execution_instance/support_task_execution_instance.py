import frappe
from frappe.model.document import Document


class SupportTaskExecutionInstance(Document):

	def validate(self):
		if self.is_new():
			self._validate_duplicate_occurrence()

		self._validate_execution_data()
		self._validate_status_transition()
		
	def _validate_status_transition(self):
		"""Validate supported execution lifecycle transitions."""

		if self.is_new():
			return

		old_status = self.get_db_value("status")

		if not old_status or old_status == self.status:
			return

		allowed_transitions = {
			"Pending": {
				"In Progress",
				"Cancelled",
				"Missed",
			},
			"In Progress": {
				"Delivered",
				"Partially Completed",
				"Refused / Declined",
				"Not Applicable",
				"Missed",
				"Cancelled",
			},
			"Overdue": {
				"In Progress",
				"Missed",
				"Cancelled",
			},
		}

		allowed = allowed_transitions.get(old_status, set())

		if self.status not in allowed:
			frappe.throw(
				f"Invalid execution status transition: "
				f"{old_status} → {self.status}"
			)
	def _validate_duplicate_occurrence(self):
		"""Prevent multiple execution instances for the same task occurrence."""

		if not self.support_task:
			return

		if not self.scheduled_date:
			return

		filters = {
			"support_task": self.support_task,
			"scheduled_date": self.scheduled_date,
			"docstatus": ["<", 2],
		}

		if self.scheduled_time:
			filters["scheduled_time"] = self.scheduled_time

		if self.name:
			filters["name"] = ["!=", self.name]

		existing = frappe.db.exists(
			"Support Task Execution Instance",
			filters,
		)

		if existing:
			frappe.throw(
				"An execution instance already exists for this scheduled task occurrence."
		)
	def _validate_execution_data(self):
		terminal_statuses = {
			"Delivered",
			"Partially Completed",
			"Refused / Declined",
			"Not Applicable",
			"Missed",
			"Cancelled",
		}

		if self.status in terminal_statuses:
			if not self.executed_by:
				frappe.throw(
					"Executed By is required when an execution is completed."
				)

			if not self.actual_execution_time:
				frappe.throw(
					"Actual Execution Time is required when an execution is completed."
				)

		if self.follow_up_required and not self.execution_notes:
			frappe.throw(
				"Execution Notes / Outcome Details are required when follow-up is required."
			)

		if self.status == "Delivered":
			self.outcome = self.outcome or "Completed"

		elif self.status == "Partially Completed":
			self.outcome = "Partially Completed"

		elif self.status == "Missed":
			self.outcome = "Missed"

		elif self.status == "Cancelled":
			self.outcome = "Cancelled"

		elif self.status == "Not Applicable":
			self.outcome = "Not Applicable"

		elif self.status == "Refused / Declined":
			self.outcome = "Refused / Declined"