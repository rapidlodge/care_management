import frappe
from frappe import _
from frappe.model.document import Document


class ParticipantHealthAlertAcknowledgement(Document):
	def before_insert(self):
		alert = frappe.get_doc("Participant Health Alert", self.health_alert)
		self.participant = alert.participant
		self.alert_version = str(alert.modified)
		self.acknowledged_by = frappe.session.user
		self.acknowledged_on = frappe.utils.now_datetime()

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Alert acknowledgements are immutable."))

	def on_trash(self):
		frappe.throw(_("Alert acknowledgements cannot be deleted."))
