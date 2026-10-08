"""Install specialist roles before schema sync; migrate legacy fields afterward."""

import hashlib

import frappe
from frappe import _

ROLE_DEFINITIONS = {
	"Clinical Lead": {"desk_access": 1, "disabled": 0, "is_custom": 0},
	"Privacy Officer": {"desk_access": 1, "disabled": 0, "is_custom": 0},
}
BATCH_SIZE = 50
MIGRATION_LOCK = "care_management:participant-contact-alert-migration"
SOURCE_FIELDS = (
	"name", "creation", "pharmacist_name", "pharmacist_contact_number",
	"risk_or_alert_present", "risk_or_alert", "information_about_risk_or_alert",
)


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


def run_guarded_migration(*, batch_size=BATCH_SIZE, commit_batches=True):
	"""Migrate deterministic batches while holding one process-wide lock."""
	bootstrap_specialist_roles()
	_validate_migration_contract()
	batch_size = int(batch_size)
	if batch_size < 1 or batch_size > BATCH_SIZE:
		frappe.throw(_("The migration batch size is outside the approved bound."))
	result = {"contacts": 0, "alerts": 0, "batches": 0}
	with frappe.cache.lock(MIGRATION_LOCK, timeout=900, blocking_timeout=1):
		cursor = ""
		while True:
			sources = _get_source_batch(cursor, batch_size)
			if not sources:
				break
			savepoint = f"contact_alert_batch_{result['batches']}"
			frappe.db.savepoint(savepoint)
			try:
				for source in sources:
					result["contacts"] += _migrate_pharmacist(source)
					result["alerts"] += _migrate_health_alert(source)
				_verify_batch(sources)
			except Exception:
				frappe.db.rollback(save_point=savepoint)
				raise
			result["batches"] += 1
			cursor = sources[-1].name
			if commit_batches:
				frappe.db.commit()
	return result


def _validate_migration_contract():
	for doctype, required_fields in {
		"Participant Contact": {"participant", "legacy_source_reference"},
		"Participant Health Alert": {"participant", "migration_key"},
		"Participant Health Alert Acknowledgement": {"participant", "acknowledgement_key"},
	}.items():
		if not frappe.db.exists("DocType", doctype):
			frappe.throw(_("Protected participant safety metadata is incomplete."))
		meta = frappe.get_meta(doctype)
		if any(not meta.has_field(field) for field in required_fields):
			frappe.throw(_("Protected participant safety metadata is incomplete."))
	for role in ROLE_DEFINITIONS:
		if not frappe.db.exists("Role", role):
			frappe.throw(_("Specialist role installation is incomplete."))


def _get_source_batch(cursor, batch_size):
	columns = ", ".join(f"`{field}`" for field in SOURCE_FIELDS)
	return frappe.db.sql(
		f"""select {columns} from `tabParticipant Profile`
		where `name` > %s order by `name` asc limit %s for update""",
		(cursor, batch_size), as_dict=True,
	)


def _source_key(kind, participant):
	return f"legacy-{kind}:" + hashlib.sha256(participant.encode()).hexdigest()


def _migrate_pharmacist(source):
	display_name = (source.pharmacist_name or "").strip()
	phone = (source.pharmacist_contact_number or "").strip()
	if not display_name and not phone:
		return 0
	if not display_name:
		frappe.throw(_("A legacy pharmacist contact is incomplete."))
	key = _source_key("contact", source.name)
	existing = frappe.get_all("Participant Contact", filters={"legacy_source_reference": key},
		fields=["name", "participant", "display_name", "primary_phone", "legacy_source_reference"])
	if not existing:
		existing = frappe.get_all("Participant Contact",
			filters={"participant": source.name, "contact_type": "Pharmacist"},
			fields=["name", "participant", "display_name", "primary_phone", "legacy_source_reference"])
	if existing:
		row = existing[0]
		if (len(existing) != 1 or row.participant != source.name or row.display_name != display_name
			or (row.primary_phone or "") != phone
			or (row.legacy_source_reference and row.legacy_source_reference != key)):
			frappe.throw(_("A conflicting migrated pharmacist contact exists."))
		if not row.legacy_source_reference:
			frappe.db.set_value("Participant Contact", row.name, "legacy_source_reference", key)
		return 0
	doc = frappe.get_doc({
		"doctype": "Participant Contact", "participant": source.name,
		"contact_type": "Pharmacist", "display_name": display_name, "primary_phone": phone,
		"relationship_description": "Migrated legacy pharmacist contact", "priority": 1,
		"verification_status": "Unverified", "status": "Active", "legacy_source_reference": key,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return 1


def _migrate_health_alert(source):
	if (source.risk_or_alert_present != "Yes" and not source.risk_or_alert
		and not source.information_about_risk_or_alert):
		return 0
	category = {"Medical": "Clinical", "Behavioural": "Behavioural",
		"Environmental": "Environmental", "Safety": "Safety", "Self-Harm": "Self-Harm"}.get(
			source.risk_or_alert, "Other")
	key = _source_key("alert", source.name)
	legacy_reference = "legacy-participant-profile:" + hashlib.sha256(source.name.encode()).hexdigest()
	fields = ["name", "participant", "category", "status", "verification_status",
		"source_reference", "migration_key"]
	existing = frappe.get_all("Participant Health Alert", filters={"migration_key": key}, fields=fields)
	if not existing:
		existing = frappe.get_all("Participant Health Alert",
			filters={"source_type": "Legacy Participant Profile", "source_reference": legacy_reference},
			fields=fields)
	if existing:
		row = existing[0]
		if (len(existing) != 1 or row.participant != source.name or row.category != category
			or row.status != "Draft" or row.verification_status != "Unverified"
			or row.source_reference != legacy_reference or (row.migration_key and row.migration_key != key)):
			frappe.throw(_("A conflicting migrated participant health alert exists."))
		if not row.migration_key:
			frappe.db.set_value("Participant Health Alert", row.name, "migration_key", key)
		return 0
	doc = frappe.get_doc({
		"doctype": "Participant Health Alert", "participant": source.name, "category": category,
		"severity": "Moderate", "concise_summary": "Legacy participant alert requires clinical verification",
		"supporting_detail": source.information_about_risk_or_alert or "",
		"source_type": "Legacy Participant Profile", "source_reference": legacy_reference,
		"migration_key": key, "verification_status": "Unverified",
		"effective_from": source.creation, "status": "Draft",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return 1


def _verify_batch(sources):
	for source in sources:
		if ((source.pharmacist_name or "").strip() or (source.pharmacist_contact_number or "").strip()):
			if not frappe.db.exists("Participant Contact", {"legacy_source_reference": _source_key("contact", source.name)}):
				frappe.throw(_("Participant contact migration verification failed."))
		if (source.risk_or_alert_present == "Yes" or source.risk_or_alert
			or source.information_about_risk_or_alert):
			if not frappe.db.exists("Participant Health Alert", {"migration_key": _source_key("alert", source.name)}):
				frappe.throw(_("Participant health alert migration verification failed."))


def execute():
	"""Compatibility marker: data movement is post-fixture, never patch-time."""
	bootstrap_specialist_roles()
