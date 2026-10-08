import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantHealthAlertAcknowledgement(Document):
	def before_insert(self):
		alert = frappe.get_doc("Participant Health Alert", self.health_alert)
		if self.participant and self.participant != alert.participant:
			raise frappe.PermissionError
		if alert.status != "Active" or alert.verification_status != "Verified" or not alert.acknowledgement_required:
			frappe.throw(_("This health alert is not eligible for acknowledgement."))
		if not frappe.has_permission("Participant Health Alert", "read", doc=alert, user=frappe.session.user):
			raise frappe.PermissionError
		self.participant = alert.participant
		self.alert_version = str(alert.modified)
		self.acknowledged_by = frappe.session.user
		self.acknowledged_on = frappe.utils.now_datetime()
		self.acknowledgement_key = f"{alert.name}:{self.alert_version}:{self.acknowledged_by}"

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Alert acknowledgements are immutable."))

	def on_trash(self):
		frappe.throw(_("Alert acknowledgements cannot be deleted."))
