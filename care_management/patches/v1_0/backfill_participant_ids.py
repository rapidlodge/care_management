"""Backfill immutable participant identifiers after schema synchronization."""

import frappe

from care_management.care_management.participant_identity import (
	generate_participant_id,
	is_valid_participant_id,
)

LOCK_NAME = "care_management_participant_id_backfill"
MAX_GENERATION_ATTEMPTS = 32


def execute():
	if not frappe.db.has_column("Participant Profile", "participant_id"):
		frappe.throw("Participant Profile.participant_id is not installed")

	lock_acquired = frappe.db.sql("select get_lock(%s, 30)", (LOCK_NAME,))[0][0]
	if lock_acquired != 1:
		frappe.throw("Could not acquire the participant identifier backfill lock")
	try:
		return _backfill_participant_ids()
	finally:
		frappe.db.sql("select release_lock(%s)", (LOCK_NAME,))


def _backfill_participant_ids():
	rows = frappe.db.get_all(
		"Participant Profile",
		fields=["name", "participant_id"],
		order_by="name asc",
	)
	existing = set()
	missing = []
	for row in rows:
		participant_id = row.get("participant_id")
		if not participant_id:
			missing.append(row.name)
			continue
		if not is_valid_participant_id(participant_id):
			frappe.throw("Participant identifier backfill found a malformed existing value")
		if participant_id in existing:
			frappe.throw("Participant identifier backfill found a duplicate existing value")
		existing.add(participant_id)

	assignments = []
	for name in missing:
		for _attempt in range(MAX_GENERATION_ATTEMPTS):
			candidate = generate_participant_id()
			if candidate not in existing:
				existing.add(candidate)
				assignments.append((name, candidate))
				break
		else:
			frappe.throw("Participant identifier generation exhausted its collision limit")

	for name, participant_id in assignments:
		frappe.db.set_value(
			"Participant Profile",
			name,
			"participant_id",
			participant_id,
			update_modified=False,
		)
	return len(assignments)
