"""Stable, permission-guarded participant identity helpers."""

import re
import secrets

import frappe

PARTICIPANT_ID_PREFIX = "PTP-"
PARTICIPANT_ID_PATTERN = re.compile(r"^PTP-[0-9a-f]{32}$")
PARTICIPANT_ID_LENGTH = 36


def generate_participant_id():
	return PARTICIPANT_ID_PREFIX + secrets.token_hex(16)


def is_valid_participant_id(value):
	return isinstance(value, str) and PARTICIPANT_ID_PATTERN.fullmatch(value) is not None


def resolve_participant_id(participant_id, user=None, permission_type="read"):
	"""Return a permitted Participant Profile name, otherwise fail closed."""
	if not is_valid_participant_id(participant_id):
		return None

	from care_management.care_management import permissions

	resolved_user = permissions.normalize_user(user)
	if not resolved_user:
		return None

	meta = frappe.get_meta("Participant Profile")
	fields = ["name"]
	for optional_field in ("disabled", "archived"):
		if meta.has_field(optional_field):
			fields.append(optional_field)

	rows = frappe.db.get_all(
		"Participant Profile",
		filters={"participant_id": participant_id},
		fields=fields,
		limit=2,
	)
	if len(rows) != 1:
		return None
	row = rows[0]
	if row.get("disabled") or row.get("archived"):
		return None
	participant = row.get("name")
	if not participant:
		return None
	if not permissions.has_participant_document_permission(
		frappe.get_doc("Participant Profile", participant),
		permission_type,
		resolved_user,
	):
		return None
	if not frappe.has_permission(
		"Participant Profile",
		permission_type,
		doc=participant,
		user=resolved_user,
	):
		return None
	return participant
