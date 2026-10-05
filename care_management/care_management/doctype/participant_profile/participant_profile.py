# Copyright (c) 2026, Hexflow Australia and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from care_management.care_management.participant_identity import (
	generate_participant_id,
	is_valid_participant_id,
)
from care_management.care_management.prohibited_storage import reject_prohibited_mygov_storage


class ParticipantProfile(Document):
	PROTECTED_SOURCE_FIELDS = frozenset(
		{
			"marital_status",
			"religious_or_spiritual",
			"religion",
			"religious_or_cultural_needs",
			"cald",
			"atsi",
			"interpreter_required",
			"english_ability",
			"interpreter_language_required",
			"receive_mobility_allowance",
			"medicare_number",
			"crn_number",
			"veteran_affairs_details",
			"companion_card",
			"my_aged_care_number",
		}
	)

	def before_insert(self):
		reject_prohibited_mygov_storage(self)
		if self.participant_id:
			frappe.throw(_("Participant ID is assigned by the server."))
		self.participant_id = generate_participant_id()
		self._discard_deprecated_protected_values()

	def validate(self):
		reject_prohibited_mygov_storage(self)
		self.validate_participant_id()
		self.validate_deprecated_protected_fields()
		self.validate_conditional_mandatory_fields()

	def validate_participant_id(self):
		if not is_valid_participant_id(self.participant_id):
			frappe.throw(_("Participant ID is missing or invalid."))
		if self.is_new():
			return
		persisted = frappe.db.get_value("Participant Profile", self.name, "participant_id")
		if persisted != self.participant_id:
			frappe.throw(_("Participant ID cannot be changed after assignment."))

	def _discard_deprecated_protected_values(self):
		for fieldname in self.PROTECTED_SOURCE_FIELDS:
			self.set(fieldname, None)

	def validate_deprecated_protected_fields(self):
		"""Keep migrated columns as immutable rollback evidence until later removal."""
		if self.is_new():
			return
		attempted_fields = self.PROTECTED_SOURCE_FIELDS.intersection(self.__dict__)
		if not attempted_fields:
			return
		persisted = frappe.db.get_value(
			"Participant Profile",
			self.name,
			sorted(attempted_fields),
			as_dict=True,
		)
		if not persisted:
			frappe.throw(_("Participant Profile no longer exists."))
		for fieldname in attempted_fields:
			if str(self.get(fieldname) or "") != str(persisted.get(fieldname) or ""):
				frappe.throw(
					_("Protected participant details must be updated on Participant Sensitive Identity."),
					frappe.PermissionError,
				)

	def validate_conditional_mandatory_fields(self):
		"""
		Belt-and-braces server-side check mirroring the client-side
		mandatory_depends_on rules, in case records are created via
		API / data import rather than the form UI.
		"""
		checks = [
			(self.risk_or_alert_present == "Yes", "risk_or_alert", _("Risk or Alert")),
			(self.end_of_life_plan == "Yes", "date_of_last_elp_meeting", _("Date of last ELP meeting")),
			(self.bsp_plan == "Yes", "bsp_plan_review_date", _("BSP Plan Review Date")),
		]
		for condition, fieldname, label in checks:
			if condition and not self.get(fieldname):
				frappe.throw(
					_("{0} is mandatory when the related flag above is set to Yes.").format(label),
					title=_("Missing Required Field"),
				)
