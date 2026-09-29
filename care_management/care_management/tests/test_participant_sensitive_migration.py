from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.doctype.participant_profile.participant_profile import (
	ParticipantProfile,
)
from care_management.care_management.tests.helpers import (
	make_r4_participant,
	make_r4_sensitive_identity,
)
from care_management.patches.v1_0 import migrate_participant_sensitive_identity as migration


class TestParticipantSensitiveMigration(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant = make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True)
		self._set_source_values(self.participant.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def _set_source_values(self, participant):
		values = {fieldname: None for fieldname in migration.SOURCE_FIELDS}
		values.update(
			{
				"marital_status": "Single",
				"religious_or_spiritual": "No",
				"religion": "No Religion",
				"cald": "No",
				"atsi": "Neither",
				"interpreter_required": "No",
				"english_ability": "Fluent",
				"receive_mobility_allowance": "No",
				"medicare_number": "5234567890",
				"crn_number": "R4-MIGRATION-CRN",
				"companion_card": "No",
			}
		)
		frappe.db.set_value("Participant Profile", participant, values, update_modified=False)

	def _target(self, participant=None):
		return frappe.db.get_value(
			"Participant Sensitive Identity",
			{"participant": participant or self.participant.name},
			"name",
		)

	def test_01_migration_creates_one_target_per_participant(self):
		before = frappe.db.count("Participant Sensitive Identity")
		created = migration.migrate_participant_sensitive_identity()
		self.assertEqual(created, 1)
		self.assertEqual(frappe.db.count("Participant Sensitive Identity"), before + 1)

	def test_02_all_approved_fields_match_by_safe_digest(self):
		migration.migrate_participant_sensitive_identity()
		source = next(row for row in migration._source_rows() if row.name == self.participant.name)
		target = frappe.db.get_value(
			"Participant Sensitive Identity",
			self._target(),
			["participant", *migration.SOURCE_FIELDS],
			as_dict=True,
		)
		self.assertEqual(
			migration._payload_digest(dict(target)),
			migration._payload_digest(migration._target_payload(source)),
		)

	def test_03_second_run_is_idempotent(self):
		self.assertEqual(migration.migrate_participant_sensitive_identity(), 1)
		self.assertEqual(migration.migrate_participant_sensitive_identity(), 0)

	def test_04_missing_stable_identifier_fails_closed(self):
		frappe.db.set_value(
			"Participant Profile", self.participant.name, "participant_id", None, update_modified=False
		)
		self.assertRaises(frappe.ValidationError, migration.migrate_participant_sensitive_identity)

	def test_05_malformed_stable_identifier_fails_closed(self):
		frappe.db.set_value(
			"Participant Profile", self.participant.name, "participant_id", "invalid", update_modified=False
		)
		self.assertRaises(frappe.ValidationError, migration.migrate_participant_sensitive_identity)

	def test_06_conflicting_existing_target_fails_closed(self):
		make_r4_sensitive_identity(self.participant.name, marital_status="Married").insert(
			ignore_permissions=True
		)
		self.assertRaises(frappe.ValidationError, migration.migrate_participant_sensitive_identity)

	def test_07_partial_run_resumes_without_rewriting_verified_target(self):
		source = next(row for row in migration._source_rows() if row.name == self.participant.name)
		doc = frappe.get_doc(
			{"doctype": "Participant Sensitive Identity", **migration._target_payload(source)}
		).insert(ignore_permissions=True)
		modified = frappe.db.get_value(doc.doctype, doc.name, "modified")
		self.assertEqual(migration.migrate_participant_sensitive_identity(), 0)
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "modified"), modified)

	def test_08_database_uniqueness_rejects_duplicate_target(self):
		make_r4_sensitive_identity(self.participant.name).insert(ignore_permissions=True)
		self.assertRaises(
			frappe.ValidationError,
			make_r4_sensitive_identity(self.participant.name).insert,
			ignore_permissions=True,
		)

	def test_09_unavailable_application_lock_fails_without_write(self):
		with patch.object(migration, "_acquire_lock", return_value=False):
			self.assertRaises(frappe.ValidationError, migration.migrate_participant_sensitive_identity)
		self.assertFalse(self._target())

	def test_10_source_processing_order_is_deterministic(self):
		make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True)
		rows = migration._source_rows()
		self.assertEqual([row.name for row in rows], sorted(row.name for row in rows))

	def test_11_prohibited_and_later_scope_fields_are_excluded(self):
		self.assertEqual(set(migration.SOURCE_FIELDS), ParticipantProfile.PROTECTED_SOURCE_FIELDS)
		for fieldname in ("mygov_account", "primary_disability", "risk_or_alert", "funding_type"):
			self.assertNotIn(fieldname, migration.SOURCE_FIELDS)

	def test_12_later_scope_source_fields_remain_unchanged(self):
		before = frappe.db.get_value(
			"Participant Profile", self.participant.name, ["funding_type", "primary_disability"], as_dict=True
		)
		migration.migrate_participant_sensitive_identity()
		after = frappe.db.get_value(
			"Participant Profile", self.participant.name, ["funding_type", "primary_disability"], as_dict=True
		)
		self.assertEqual(before, after)

	def test_13_canonical_name_and_links_are_preserved(self):
		name = self.participant.name
		migration.migrate_participant_sensitive_identity()
		self.assertTrue(frappe.db.exists("Participant Profile", name))
		self.assertEqual(
			frappe.db.get_value("Participant Sensitive Identity", self._target(), "participant"), name
		)

	def test_14_insert_failure_rolls_back_partial_batch(self):
		other = make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True)
		self._set_source_values(other.name)
		real_get_doc = frappe.get_doc
		calls = 0

		def fail_second_target(*args, **kwargs):
			nonlocal calls
			doc = real_get_doc(*args, **kwargs)
			if getattr(doc, "doctype", None) == "Participant Sensitive Identity":
				calls += 1
				if calls == 2:
					raise frappe.ValidationError("synthetic migration failure")
			return doc

		with patch.object(migration.frappe, "get_doc", side_effect=fail_second_target):
			self.assertRaises(frappe.ValidationError, migration.migrate_participant_sensitive_identity)
		self.assertFalse(self._target(self.participant.name))
		self.assertFalse(self._target(other.name))
