import re

import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantSensitiveIdentity(Document):
	def validate(self):
		self._validate_canonical_participant()
		self._validate_participant_immutable()
		self._validate_one_to_one()
		self._validate_medicare_number()
		self._validate_interpreter_language()

	def before_rename(self, old, new, merge=False):
		frappe.throw(_("Participant Sensitive Identity names cannot be changed."))

	def on_trash(self):
		frappe.throw(_("Participant Sensitive Identity records cannot be deleted."))

	def _validate_canonical_participant(self):
		if not self.participant or not frappe.db.exists("Participant Profile", self.participant):
			frappe.throw(_("A valid canonical Participant Profile is required."))

	def _validate_participant_immutable(self):
		if self.is_new():
			return
		persisted = frappe.db.get_value(self.doctype, self.name, "participant")
		if persisted != self.participant:
			frappe.throw(_("The canonical participant cannot be changed."))

	def _validate_one_to_one(self):
		existing = frappe.db.get_value(self.doctype, {"participant": self.participant}, "name")
		if existing and existing != self.name:
			frappe.throw(_("Protected participant details already exist."))

	def _validate_medicare_number(self):
		if not self.medicare_number:
			return
		cleaned = re.sub(r"\s+", "", self.medicare_number)
		if not re.fullmatch(r"\d{10,11}", cleaned):
			frappe.throw(_("Medicare Number must be 10 or 11 digits."))

	def _validate_interpreter_language(self):
		if self.interpreter_required == "Yes" and not self.interpreter_language_required:
			frappe.throw(_("Interpreter Language Required Specify is mandatory."))
