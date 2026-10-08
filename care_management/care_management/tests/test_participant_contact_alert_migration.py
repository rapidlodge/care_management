import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import ensure_r2c1_participant
from care_management.patches.v1_0 import migrate_participant_contacts_and_health_alerts as migration

FIXTURE = Path(frappe.get_app_path("care_management", "fixtures", "role.json"))


class TestParticipantContactAlertMigration(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_specialist_role_fixture_matches_install_contract(self):
		fixture = json.loads(FIXTURE.read_text())
		self.assertEqual({row["role_name"] for row in fixture}, set(migration.ROLE_DEFINITIONS))
		self.assertTrue(all(row["desk_access"] and not row["disabled"] for row in fixture))

	def test_install_hooks_separate_role_bootstrap_from_data_migration(self):
		self.assertIn("bootstrap_specialist_roles", str(frappe.get_hooks("before_install", app_name="care_management")))
		self.assertIn("bootstrap_specialist_roles", str(frappe.get_hooks("before_migrate", app_name="care_management")))
		self.assertIn("run_guarded_migration", str(frappe.get_hooks("after_sync", app_name="care_management")))
		self.assertIn("run_guarded_migration", str(frappe.get_hooks("after_migrate", app_name="care_management")))

	def test_source_keys_are_deterministic_and_domain_separated(self):
		first = migration._source_key("contact", "participant-a")
		self.assertEqual(first, migration._source_key("contact", "participant-a"))
		self.assertNotEqual(first, migration._source_key("alert", "participant-a"))

	def test_batch_size_is_bounded(self):
		with patch.object(migration, "bootstrap_specialist_roles"), patch.object(
			migration, "_validate_migration_contract"
		):
			for invalid in (0, migration.BATCH_SIZE + 1):
				self.assertRaises(frappe.ValidationError, migration.run_guarded_migration,
					batch_size=invalid, commit_batches=False)

	def test_multiple_batches_use_stable_cursor_and_commit_each_verified_batch(self):
		batches = [[frappe._dict(name="A")], [frappe._dict(name="B")], []]
		lock = MagicMock()
		lock.__enter__.return_value = lock
		with patch.object(migration, "bootstrap_specialist_roles"), patch.object(
			migration, "_validate_migration_contract"
		), patch.object(migration, "_get_source_batch", side_effect=batches) as get_batch, patch.object(
			migration, "_migrate_pharmacist", return_value=0
		), patch.object(migration, "_migrate_health_alert", return_value=0), patch.object(
			migration, "_verify_batch"
		), patch.object(frappe.cache, "lock", return_value=lock), patch.object(frappe.db, "commit") as commit:
			result = migration.run_guarded_migration(batch_size=1)
		self.assertEqual(result["batches"], 2)
		self.assertEqual(get_batch.call_args_list, [call("", 1), call("A", 1), call("B", 1)])
		self.assertEqual(commit.call_count, 2)

	def test_failing_batch_rolls_back_only_current_savepoint(self):
		batches = [[frappe._dict(name="A")], []]
		lock = MagicMock()
		lock.__enter__.return_value = lock
		with patch.object(migration, "bootstrap_specialist_roles"), patch.object(
			migration, "_validate_migration_contract"
		), patch.object(migration, "_get_source_batch", side_effect=batches), patch.object(
			migration, "_migrate_pharmacist", side_effect=RuntimeError("controlled failure")
		), patch.object(frappe.cache, "lock", return_value=lock), patch.object(
			frappe.db, "rollback"
		) as rollback:
			self.assertRaises(RuntimeError, migration.run_guarded_migration, batch_size=1,
				commit_batches=False)
		rollback.assert_called_once_with(save_point="contact_alert_batch_0")

	def test_lock_contention_fails_without_processing(self):
		with patch.object(migration, "bootstrap_specialist_roles"), patch.object(
			migration, "_validate_migration_contract"
		), patch.object(frappe.cache, "lock", side_effect=RuntimeError("lock unavailable")), patch.object(
			migration, "_get_source_batch"
		) as get_batch:
			self.assertRaises(RuntimeError, migration.run_guarded_migration, commit_batches=False)
		get_batch.assert_not_called()

	def test_real_target_creation_and_second_run_are_idempotent(self):
		participant = ensure_r2c1_participant("R4 Migration", "6234567890")
		frappe.db.set_value("Participant Profile", participant, {
			"pharmacist_name": "R4 Migration Pharmacist", "pharmacist_contact_number": "0400000001",
			"risk_or_alert_present": "Yes", "risk_or_alert": "Safety",
			"information_about_risk_or_alert": "Synthetic migration fixture",
		})
		source = frappe.db.get_value("Participant Profile", participant, list(migration.SOURCE_FIELDS), as_dict=True)
		self.assertEqual(migration._migrate_pharmacist(source), 1)
		self.assertEqual(migration._migrate_health_alert(source), 1)
		self.assertEqual(migration._migrate_pharmacist(source), 0)
		self.assertEqual(migration._migrate_health_alert(source), 0)

	def test_conflicting_contact_target_fails_closed(self):
		participant = ensure_r2c1_participant("R4 Migration Conflict", "62345678901")
		frappe.db.set_value("Participant Profile", participant, {
			"pharmacist_name": "Expected Pharmacist", "pharmacist_contact_number": "0400000002",
		})
		source = frappe.db.get_value("Participant Profile", participant, list(migration.SOURCE_FIELDS), as_dict=True)
		frappe.get_doc({"doctype": "Participant Contact", "participant": participant,
			"contact_type": "Pharmacist", "display_name": "Conflicting Pharmacist", "priority": 99,
			"verification_status": "Unverified", "status": "Active"}).insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, migration._migrate_pharmacist, source)

	def test_source_batch_query_has_limit_order_and_row_lock(self):
		with patch.object(frappe.db, "sql", return_value=[]) as sql:
			migration._get_source_batch("cursor", 7)
		query = " ".join(sql.call_args.args[0].lower().split())
		self.assertIn("order by `name` asc limit %s for update", query)
		self.assertEqual(sql.call_args.args[1], ("cursor", 7))
