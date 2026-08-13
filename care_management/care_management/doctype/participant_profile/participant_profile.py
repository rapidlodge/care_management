# Copyright (c) 2026, Hexflow Australia and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantProfile(Document):
	def validate(self):
		self.validate_medicare_number()
		self.validate_conditional_mandatory_fields()

	def validate_medicare_number(self):
		"""Australian Medicare numbers are 10 or 11 digits."""
		if self.medicare_number:
			cleaned = re.sub(r"\s+", "", self.medicare_number)
			if not re.match(r"^\d{10,11}$", cleaned):
				frappe.throw(
					_("Medicare Number must be 10 or 11 digits."),
					title=_("Invalid Medicare Number"),
				)

	def validate_conditional_mandatory_fields(self):
		"""
		Belt-and-braces server-side check mirroring the client-side
		mandatory_depends_on rules, in case records are created via
		API / data import rather than the form UI.
		"""
		checks = [
			(self.risk_or_alert_present == "Yes", "risk_or_alert", _("Risk or Alert")),
			(self.interpreter_required == "Yes", "interpreter_language_required", _("Interpreter Language Required Specify")),
			(self.end_of_life_plan == "Yes", "date_of_last_elp_meeting", _("Date of last ELP meeting")),
			(self.bsp_plan == "Yes", "bsp_plan_review_date", _("BSP Plan Review Date")),
		]
		for condition, fieldname, label in checks:
			if condition and not self.get(fieldname):
				frappe.throw(
					_("{0} is mandatory when the related flag above is set to Yes.").format(label),
					title=_("Missing Required Field"),
				)
