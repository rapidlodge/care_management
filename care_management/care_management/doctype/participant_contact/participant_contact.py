import re

import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantContact(Document):
	VERIFIED_IMMUTABLE_FIELDS = frozenset({
		"participant", "contact_type", "display_name", "relationship_description", "primary_phone",
		"alternate_phone", "email", "preferred_contact_method", "availability_notes", "priority",
		"verification_status", "unable_to_reach_instruction", "effective_from", "legacy_source_reference",
	})

	def validate(self):
		persisted = None if self.is_new() else frappe.db.get_value(
			self.doctype,
			self.name,
			[*self.VERIFIED_IMMUTABLE_FIELDS, "status", "effective_to", "verified_by", "verified_on"],
			as_dict=True,
		)
		persisted_verification = persisted.get("verification_status") if persisted else None
		if not self.participant or not frappe.db.exists("Participant Profile", self.participant):
			frappe.throw(_("A valid canonical participant is required."))
		if not self.is_new() and frappe.db.get_value(self.doctype, self.name, "participant") != self.participant:
			frappe.throw(_("The canonical participant cannot be changed."))
		if self.contact_type == "Emergency Contact" and not self.unable_to_reach_instruction:
			frappe.throw(_("An unable-to-reach instruction is required."))
		if int(self.priority or 0) < 1:
			frappe.throw(_("Contact priority must be a positive number."))
		if self.status == "Active":
			duplicate = frappe.db.get_value(self.doctype, {
				"participant": self.participant, "contact_type": self.contact_type,
				"priority": self.priority, "status": "Active", "name": ["!=", self.name or ""],
			}, "name")
			if duplicate:
				frappe.throw(_("An active contact already uses this priority."))
		self.normalized_contact_key = re.sub(r"\W+", "", f"{self.display_name}{self.primary_phone}{self.email}").lower()
		if persisted_verification == "Verified":
			changed = [field for field in self.VERIFIED_IMMUTABLE_FIELDS if self.get(field) != persisted.get(field)]
			if changed:
				frappe.throw(_("Verified participant contact evidence is immutable."), frappe.PermissionError)
			if any(self.get(field) != persisted.get(field) for field in ("verified_by", "verified_on")):
				frappe.throw(_("Contact verification evidence is immutable."), frappe.PermissionError)
			if persisted.status == "Inactive" and self.status != "Inactive":
				frappe.throw(_("Inactive participant contacts cannot be reactivated."), frappe.PermissionError)
		if self.verification_status == "Verified" and persisted_verification != "Verified":
			if not {"Care Manager", "Clinical Lead"}.intersection(frappe.get_roles()):
				frappe.throw(_("Clinical verification requires an authorized clinical role."), frappe.PermissionError)
			self.verified_by = frappe.session.user
			self.verified_on = frappe.utils.now_datetime()

	def on_trash(self):
		if self.verification_status == "Verified" or self.legacy_source_reference:
			frappe.throw(_("Verified participant contacts must be inactivated, not deleted."))
