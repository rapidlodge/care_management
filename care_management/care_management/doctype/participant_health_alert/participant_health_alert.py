import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantHealthAlert(Document):
	CLINICAL_FIELDS = frozenset({
		"participant", "category", "severity", "concise_summary", "response_instruction",
		"supporting_detail", "source_type", "source_reference", "migration_key", "verification_status",
		"effective_from", "effective_to", "review_date", "responsible_role", "responsible_user",
		"acknowledgement_required",
	})

	def validate(self):
		persisted = {} if self.is_new() else (frappe.db.get_value(
			self.doctype, self.name, [*self.CLINICAL_FIELDS, "status", "resolution_reason"], as_dict=True
		) or {})
		if not self.participant or not frappe.db.exists("Participant Profile", self.participant):
			frappe.throw(_("A valid canonical participant is required."))
		if not self.is_new() and frappe.db.get_value(self.doctype, self.name, "participant") != self.participant:
			frappe.throw(_("The canonical participant cannot be changed."))
		if self.status == "Active":
			for field in ("response_instruction", "effective_from", "review_date"):
				if not self.get(field):
					frappe.throw(_("Active alerts require complete response and review evidence."))
			if self.verification_status != "Verified":
				frappe.throw(_("Only verified alerts may become active."))
			conflict = frappe.db.get_value(self.doctype, {"participant": self.participant, "category": self.category, "status": "Active", "name": ["!=", self.name or ""]}, "name")
			if conflict:
				frappe.throw(_("A conflicting active alert requires manager resolution."))
		if persisted.get("verification_status") == "Verified":
			if any(self.has_value_changed(field) for field in self.CLINICAL_FIELDS):
				frappe.throw(_("Verified participant health alert evidence is immutable."), frappe.PermissionError)
		if persisted.get("status") == "Resolved":
			if self.status != "Resolved" or self.resolution_reason != persisted.get("resolution_reason"):
				frappe.throw(_("Resolved participant health alerts are immutable."), frappe.PermissionError)
		if self.verification_status == "Verified" and persisted.get("verification_status") != "Verified":
			if not {"Care Manager", "Clinical Lead"}.intersection(frappe.get_roles()):
				frappe.throw(_("Clinical verification requires an authorized clinical role."), frappe.PermissionError)
			self.verified_by = frappe.session.user
			self.verified_on = frappe.utils.now_datetime()
		if self.status == "Resolved":
			if not self.resolution_reason:
				frappe.throw(_("A resolution reason is required."))
			if persisted.get("status") != "Resolved":
				if not {"Care Manager", "Clinical Lead"}.intersection(frappe.get_roles()):
					frappe.throw(_("Alert resolution requires an authorized clinical role."), frappe.PermissionError)
				self.resolved_by = frappe.session.user
				self.resolved_on = frappe.utils.now_datetime()

	def on_trash(self):
		frappe.throw(_("Health alert history cannot be deleted."))
