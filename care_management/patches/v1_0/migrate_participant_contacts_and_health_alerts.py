"""Install specialist roles before schema sync; migrate only after fixtures."""

import hashlib

import frappe
from frappe import _

ROLE_DEFINITIONS = {
	"Clinical Lead": {"desk_access": 1, "disabled": 0, "is_custom": 0},
	"Privacy Officer": {"desk_access": 1, "disabled": 0, "is_custom": 0},
}


def bootstrap_specialist_roles():
	for name, expected in ROLE_DEFINITIONS.items():
		if not frappe.db.exists("Role", name):
			doc = frappe.get_doc({"doctype": "Role", "role_name": name, **expected})
			doc.flags.ignore_permissions = True
			doc.insert()
			continue
		actual = frappe.db.get_value("Role", name, list(expected), as_dict=True)
		if not actual or any(int(actual.get(key) or 0) != value for key, value in expected.items()):
			frappe.throw(_("Specialist role metadata conflicts with the repository contract."))


def run_guarded_migration():
	bootstrap_specialist_roles()
	for doctype in ("Participant Contact", "Participant Health Alert", "Participant Health Alert Acknowledgement"):
		if not frappe.db.exists("DocType", doctype):
			frappe.throw(_("Protected participant safety metadata is incomplete."))
	savepoint = "care_management_contact_alert_migration"
	frappe.db.savepoint(savepoint)
	try:
		created = {"contacts": 0, "alerts": 0}
		for source in frappe.get_all(
			"Participant Profile",
			fields=[
				"name", "creation", "pharmacist_name", "pharmacist_contact_number",
				"risk_or_alert_present", "risk_or_alert", "information_about_risk_or_alert",
			],
			order_by="name asc",
		):
			created["contacts"] += _migrate_pharmacist(source)
			created["alerts"] += _migrate_health_alert(source)
		return created
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise


def _migrate_pharmacist(source):
	display_name = (source.pharmacist_name or "").strip()
	phone = (source.pharmacist_contact_number or "").strip()
	if not display_name and not phone:
		return 0
	if not display_name:
		frappe.throw(_("A legacy pharmacist contact is incomplete."))
	existing = frappe.get_all(
		"Participant Contact",
		filters={"participant": source.name, "contact_type": "Pharmacist"},
		fields=["name", "display_name", "primary_phone"],
	)
	if existing:
		row = existing[0]
		if len(existing) != 1 or row.display_name != display_name or (row.primary_phone or "") != phone:
			frappe.throw(_("A conflicting migrated pharmacist contact exists."))
		return 0
	doc = frappe.get_doc({
		"doctype": "Participant Contact", "participant": source.name,
		"contact_type": "Pharmacist", "display_name": display_name,
		"primary_phone": phone, "relationship_description": "Migrated legacy pharmacist contact",
		"priority": 1, "verification_status": "Unverified", "status": "Active",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return 1


def _migrate_health_alert(source):
	if source.risk_or_alert_present != "Yes" and not source.risk_or_alert and not source.information_about_risk_or_alert:
		return 0
	category = {
		"Medical": "Clinical", "Behavioural": "Behavioural", "Environmental": "Environmental",
		"Safety": "Safety", "Self-Harm": "Self-Harm",
	}.get(source.risk_or_alert, "Other")
	source_reference = "legacy-participant-profile:" + hashlib.sha256(source.name.encode()).hexdigest()
	existing = frappe.get_all(
		"Participant Health Alert",
		filters={"source_type": "Legacy Participant Profile", "source_reference": source_reference},
		fields=["name", "participant", "category", "status", "verification_status"],
	)
	if existing:
		row = existing[0]
		if len(existing) != 1 or row.participant != source.name or row.category != category or row.status != "Draft" or row.verification_status != "Unverified":
			frappe.throw(_("A conflicting migrated participant health alert exists."))
		return 0
	doc = frappe.get_doc({
		"doctype": "Participant Health Alert", "participant": source.name, "category": category,
		"severity": "Moderate", "concise_summary": "Legacy participant alert requires clinical verification",
		"supporting_detail": source.information_about_risk_or_alert or "",
		"source_type": "Legacy Participant Profile", "source_reference": source_reference,
		"verification_status": "Unverified", "effective_from": source.creation, "status": "Draft",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return 1


def execute():
	"""Compatibility marker: data movement is post-fixture, never patch-time."""
	bootstrap_specialist_roles()
