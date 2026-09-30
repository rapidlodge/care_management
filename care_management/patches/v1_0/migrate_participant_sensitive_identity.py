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
BATCH_SIZE = 100


def execute():
	return migrate_participant_sensitive_identity()


def migrate_participant_sensitive_identity():
	if not frappe.db.table_exists(TARGET_DOCTYPE):
		frappe.throw(f"{TARGET_DOCTYPE} is not installed")
	if not _acquire_lock():
		frappe.throw("Participant sensitive-identity migration is already running")
	try:
		created = 0
		cursor = ""
		while participant_names := _source_batch(cursor):
			frappe.db.savepoint("participant_sensitive_identity_batch")
			try:
				for participant in participant_names:
					row = _locked_source_row(participant)
					if not row:
						continue
					_validate_source_rows((row,))
					created += _migrate_locked_row(row)
				_verify_batch(participant_names)
				_commit_batch()
			except Exception:
				frappe.db.rollback(save_point="participant_sensitive_identity_batch")
				raise
			cursor = participant_names[-1]
		_verify_complete()
		return created
	finally:
		_release_lock()


def _source_batch(after_name=""):
	return tuple(
		row.name
		for row in frappe.db.sql(
			"""
			select `name`
			from `tabParticipant Profile`
			where `name` > %s
			order by `name`
			limit %s
			""",
			(after_name, BATCH_SIZE),
			as_dict=True,
		)
	)


def _locked_source_row(participant):
	return _source_row(participant, for_update=True)


def _source_row(participant, for_update=False):
	fields = ", ".join(f"`{fieldname}`" for fieldname in SOURCE_FIELDS)
	lock_clause = "for update" if for_update else ""
	rows = frappe.db.sql(
		f"""
		select `name`, `participant_id`, {fields}
		from `tabParticipant Profile`
		where `name` = %s
		limit 1
		{lock_clause}
		""",
		(participant,),
		as_dict=True,
	)
	return rows[0] if rows else None


def _source_rows():
	rows = []
	cursor = ""
	while participant_names := _source_batch(cursor):
		for participant in participant_names:
			row = _source_row(participant)
			if row:
				rows.append(row)
		cursor = participant_names[-1]
	return rows


def _validate_source_rows(rows):
	if any(not row.participant_id or not is_valid_participant_id(row.participant_id) for row in rows):
		frappe.throw("Every Participant Profile must have a stable participant identifier")
	participants = [row.name for row in rows]
	if len(participants) != len(set(participants)):
		frappe.throw("Duplicate canonical participant rows detected")


def _migrate_locked_row(row):
	payload = _target_payload(row)
	existing = frappe.db.get_value(TARGET_DOCTYPE, {"participant": row.name}, "name")
	if existing:
		_validate_existing_target(existing, payload)
		return 0
	frappe.get_doc({"doctype": TARGET_DOCTYPE, **payload}).insert(ignore_permissions=True)
	created = frappe.db.get_value(TARGET_DOCTYPE, {"participant": row.name}, "name")
	if not created:
		frappe.throw("Protected participant details migration did not create a durable target")
	_validate_existing_target(created, payload)
	return 1


def _target_payload(row):
	return {"participant": row.name, **{fieldname: row.get(fieldname) for fieldname in SOURCE_FIELDS}}


def _payload_digest(payload):
	canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_existing_target(name, expected):
	actual = frappe.db.get_value(TARGET_DOCTYPE, name, ["participant", *SOURCE_FIELDS], as_dict=True)
	if not actual or _payload_digest(dict(actual)) != _payload_digest(expected):
		frappe.throw("Existing protected participant details conflict with canonical migration source")


def _verify_batch(participant_names, for_update=True):
	for participant in participant_names:
		row = _source_row(participant, for_update=for_update)
		if not row:
			continue
		name = frappe.db.get_value(TARGET_DOCTYPE, {"participant": row.name}, "name")
		if not name:
			frappe.throw("Protected participant details migration is incomplete")
		_validate_existing_target(name, _target_payload(row))


def _verify_complete():
	cursor = ""
	while participant_names := _source_batch(cursor):
		_verify_batch(participant_names, for_update=False)
		cursor = participant_names[-1]


def _commit_batch():
	frappe.db.commit()


def _acquire_lock():
	return bool(frappe.db.sql("select get_lock(%s, 0)", (LOCK_NAME,))[0][0])


def _release_lock():
	frappe.db.sql("select release_lock(%s)", (LOCK_NAME,))
