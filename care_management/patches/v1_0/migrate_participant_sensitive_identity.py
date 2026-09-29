import hashlib
import json

import frappe

from care_management.care_management.doctype.participant_profile.participant_profile import (
	ParticipantProfile,
)
from care_management.care_management.participant_identity import is_valid_participant_id

LOCK_NAME = "care_management_participant_sensitive_identity_migration"
TARGET_DOCTYPE = "Participant Sensitive Identity"
SOURCE_FIELDS = tuple(sorted(ParticipantProfile.PROTECTED_SOURCE_FIELDS))


def execute():
	return migrate_participant_sensitive_identity()


def migrate_participant_sensitive_identity():
	if not frappe.db.table_exists(TARGET_DOCTYPE):
		frappe.throw(f"{TARGET_DOCTYPE} is not installed")
	if not _acquire_lock():
		frappe.throw("Participant sensitive-identity migration is already running")
	frappe.db.savepoint("participant_sensitive_identity_migration")
	try:
		profiles = _source_rows()
		_validate_source_rows(profiles)
		created = 0
		for row in profiles:
			payload = _target_payload(row)
			existing = frappe.db.get_value(TARGET_DOCTYPE, {"participant": row.name}, "name")
			if existing:
				_validate_existing_target(existing, payload)
				continue
			frappe.get_doc({"doctype": TARGET_DOCTYPE, **payload}).insert(ignore_permissions=True)
			created += 1
		_verify_complete(profiles)
		return created
	except Exception:
		frappe.db.rollback(save_point="participant_sensitive_identity_migration")
		raise
	finally:
		_release_lock()


def _source_rows():
	fields = ", ".join(f"`{fieldname}`" for fieldname in SOURCE_FIELDS)
	return frappe.db.sql(
		f"select `name`, `participant_id`, {fields} from `tabParticipant Profile` order by `name`",
		as_dict=True,
	)


def _validate_source_rows(rows):
	if any(not row.participant_id or not is_valid_participant_id(row.participant_id) for row in rows):
		frappe.throw("Every Participant Profile must have a stable participant identifier")
	participants = [row.name for row in rows]
	if len(participants) != len(set(participants)):
		frappe.throw("Duplicate canonical participant rows detected")


def _target_payload(row):
	return {"participant": row.name, **{fieldname: row.get(fieldname) for fieldname in SOURCE_FIELDS}}


def _payload_digest(payload):
	canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_existing_target(name, expected):
	actual = frappe.db.get_value(TARGET_DOCTYPE, name, ["participant", *SOURCE_FIELDS], as_dict=True)
	if not actual or _payload_digest(dict(actual)) != _payload_digest(expected):
		frappe.throw("Existing protected participant details conflict with canonical migration source")


def _verify_complete(rows):
	if frappe.db.count(TARGET_DOCTYPE) < len(rows):
		frappe.throw("Protected participant details migration is incomplete")
	for row in rows:
		name = frappe.db.get_value(TARGET_DOCTYPE, {"participant": row.name}, "name")
		if not name:
			frappe.throw("Protected participant details migration is incomplete")
		_validate_existing_target(name, _target_payload(row))


def _acquire_lock():
	return bool(frappe.db.sql("select get_lock(%s, 0)", (LOCK_NAME,))[0][0])


def _release_lock():
	frappe.db.sql("select release_lock(%s)", (LOCK_NAME,))
