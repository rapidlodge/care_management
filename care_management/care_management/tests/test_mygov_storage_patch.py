import inspect
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.doctype.participant_profile.participant_profile import (
	ParticipantProfile,
)
from care_management.patches.v1_0 import remove_mygov_storage


class TestMyGovStoragePatch(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_01_physical_column_is_absent(self):
		self.assertFalse(frappe.db.has_column("Participant Profile", "mygov_account"))

	def test_02_live_execution_is_idempotent(self):
		with patch.object(remove_mygov_storage, "_drop_column") as drop_column:
			remove_mygov_storage.execute()
		drop_column.assert_not_called()

	def test_03_missing_column_is_a_no_op(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=False),
			patch.object(remove_mygov_storage, "_live_counts") as live_counts,
		):
			remove_mygov_storage.execute()
		live_counts.assert_not_called()

	def test_04_zero_value_state_drops_column_once(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=True),
			patch.object(
				remove_mygov_storage,
				"_live_counts",
				return_value=frappe._dict(total_rows=2, null_rows=2, blank_rows=0, nonempty_rows=0),
			),
			patch.object(remove_mygov_storage, "_history_reference_counts", return_value={"version": 0}),
			patch.object(remove_mygov_storage, "_drop_column") as drop_column,
		):
			remove_mygov_storage.execute()
		drop_column.assert_called_once_with()

	def test_05_nonempty_value_aborts_without_schema_change(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=True),
			patch.object(
				remove_mygov_storage,
				"_live_counts",
				return_value=frappe._dict(total_rows=2, null_rows=1, blank_rows=0, nonempty_rows=1),
			),
			patch.object(remove_mygov_storage, "_drop_column") as drop_column,
		):
			with self.assertRaisesRegex(frappe.ValidationError, "separate authorization"):
				remove_mygov_storage.execute()
		drop_column.assert_not_called()

	def test_06_version_reference_aborts_without_schema_change(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=True),
			patch.object(
				remove_mygov_storage,
				"_live_counts",
				return_value=frappe._dict(total_rows=2, null_rows=2, blank_rows=0, nonempty_rows=0),
			),
			patch.object(remove_mygov_storage, "_history_reference_counts", return_value={"version": 1}),
			patch.object(remove_mygov_storage, "_drop_column") as drop_column,
		):
			with self.assertRaisesRegex(frappe.ValidationError, "Historical prohibited-storage"):
				remove_mygov_storage.execute()
		drop_column.assert_not_called()

	def test_07_log_reference_aborts_without_schema_change(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=True),
			patch.object(
				remove_mygov_storage,
				"_live_counts",
				return_value=frappe._dict(total_rows=2, null_rows=2, blank_rows=0, nonempty_rows=0),
			),
			patch.object(
				remove_mygov_storage,
				"_history_reference_counts",
				return_value={"version": 0, "error_log": 1},
			),
			patch.object(remove_mygov_storage, "_drop_column") as drop_column,
		):
			with self.assertRaises(frappe.ValidationError):
				remove_mygov_storage.execute()
		drop_column.assert_not_called()

	def test_08_ddl_failure_does_not_include_a_value(self):
		with (
			patch.object(remove_mygov_storage.frappe.db, "has_column", return_value=True),
			patch.object(
				remove_mygov_storage,
				"_live_counts",
				return_value=frappe._dict(total_rows=2, null_rows=2, blank_rows=0, nonempty_rows=0),
			),
			patch.object(remove_mygov_storage, "_history_reference_counts", return_value={"version": 0}),
			patch.object(
				remove_mygov_storage,
				"_drop_column",
				side_effect=frappe.ValidationError("Injected schema failure"),
			),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "Injected schema failure") as context:
				remove_mygov_storage.execute()
		self.assertNotIn("must-not-store", str(context.exception))

	def test_09_patch_and_partial_state_remain_value_free_and_fail_closed(self):
		source = inspect.getsource(remove_mygov_storage)
		self.assertNotIn("select name", source.lower())
		self.assertNotIn("distinct", source.lower())
		self.assertNotIn("length(", source.lower())
		self.assertNotIn("mygov_account", ParticipantProfile.PROTECTED_SOURCE_FIELDS)
		self.assertIn("reject_prohibited_mygov_storage", inspect.getsource(ParticipantProfile))
