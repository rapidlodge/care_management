from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management import permissions
from care_management.care_management.tests.helpers import (
	clear_r2c1_permission_caches,
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_support_task,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)

# Standalone IntegrationTestCase module: fixtures are created explicitly because
# Frappe v16 does not support automatic dependency-ignore directives outside a
# DocType test module.


class TestParticipantAuthorization(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("A", "1234567890")
		self.participant_b = ensure_r2c1_participant("B", "12345678901")
		self.plan_a = ensure_r2c1_support_plan(self.participant_a, "A")
		self.plan_b = ensure_r2c1_support_plan(self.participant_b, "B")
		self.task_a = ensure_r2c1_support_task(self.plan_a, "A")
		self.task_b = ensure_r2c1_support_task(self.plan_b, "B")
		self.system_manager = ensure_r2c1_user("System Manager", ["System Manager"])
		self.care_manager = ensure_r2c1_user("Care Manager", ["Care Manager"])
		self.coordinator = ensure_r2c1_user("Support Coordinator", ["Support Coordinator"])
		self.worker_a = ensure_r2c1_user("Support Worker A", ["Support Worker"])
		self.worker_b = ensure_r2c1_user("Support Worker B", ["Support Worker"])
		self.scoped_worker = ensure_r2c1_user("Scoped Worker", ["Support Worker"])
		self.plan_scoped_worker = ensure_r2c1_user("Plan Scoped Worker", ["Support Worker"])
		self.unmapped_worker = ensure_r2c1_user("Unmapped Worker", ["Support Worker"])
		ensure_r2c1_user_permission(self.care_manager, self.participant_a)
		ensure_r2c1_user_permission(self.coordinator, self.participant_a)
		ensure_r2c1_user_permission(self.worker_a, self.participant_a)
		ensure_r2c1_user_permission(self.worker_b, self.participant_b)
		ensure_r2c1_user_permission(self.scoped_worker, self.participant_a, applicable_for="Support Task")
		ensure_r2c1_user_permission(self.plan_scoped_worker, self.participant_a, applicable_for="Support Plan")
		ensure_r2c1_task_assignment(self.task_a, self.worker_a)
		ensure_r2c1_task_assignment(self.task_b, self.worker_b)
		ensure_r2c1_task_assignment(self.task_a, self.scoped_worker)
		ensure_r2c1_task_assignment(self.task_a, self.plan_scoped_worker)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_guest_cannot_access_participant(self):
		self.assertFalse(permissions.has_participant_access(self.participant_a, user="Guest"))

	def test_user_without_grant_is_denied(self):
		self.assertFalse(permissions.has_participant_access(self.participant_a, user=self.unmapped_worker))

	def test_care_manager_accesses_only_granted_participant(self):
		self.assertTrue(permissions.has_participant_access(self.participant_a, user=self.care_manager))
		self.assertFalse(permissions.has_participant_access(self.participant_b, user=self.care_manager))

	def test_support_coordinator_accesses_only_granted_participant(self):
		self.assertTrue(permissions.has_participant_access(self.participant_a, user=self.coordinator))
		self.assertFalse(permissions.has_participant_access(self.participant_b, user=self.coordinator))

	def test_worker_with_grant_and_assignment_can_access_active_task(self):
		self.assertTrue(permissions.can_access_task(self.task_a, user=self.worker_a))

	def test_worker_with_grant_without_assignment_cannot_perform_task_action(self):
		self.assertFalse(permissions.can_access_task(self.task_b, user=self.worker_a))

	def test_worker_with_assignment_without_participant_grant_cannot_perform_task_action(self):
		ensure_r2c1_task_assignment(self.task_a, self.unmapped_worker)
		self.assertFalse(permissions.can_access_task(self.task_a, user=self.unmapped_worker))

	def test_restricted_task_grant_does_not_grant_generic_participant_access(self):
		self.assertFalse(permissions.has_participant_access(self.participant_a, user=self.scoped_worker))

	def test_restricted_task_grant_allows_task_scoped_participant_access(self):
		self.assertTrue(
			permissions.has_participant_access(
				self.participant_a,
				user=self.scoped_worker,
				applicable_for="Support Task",
			)
		)

	def test_restricted_task_grant_denies_other_scoped_participant_access(self):
		self.assertFalse(
			permissions.has_participant_access(
				self.participant_a,
				user=self.scoped_worker,
				applicable_for="Support Plan",
			)
		)

	def test_restricted_task_grant_allows_assigned_task_access(self):
		self.assertTrue(permissions.can_access_task(self.task_a, user=self.scoped_worker))

	def test_plan_scoped_grant_allows_only_plan_context(self):
		self.assertFalse(permissions.has_participant_access(self.participant_a, user=self.plan_scoped_worker))
		self.assertTrue(
			permissions.has_participant_access(
				self.participant_a,
				user=self.plan_scoped_worker,
				applicable_for="Support Plan",
			)
		)
		self.assertFalse(
			permissions.has_participant_access(
				self.participant_a,
				user=self.plan_scoped_worker,
				applicable_for="Support Task",
			)
		)

	def test_plan_scoped_grant_does_not_allow_task_action(self):
		self.assertFalse(permissions.can_access_task(self.task_a, user=self.plan_scoped_worker))

	def test_another_worker_cannot_access_other_workers_task(self):
		self.assertFalse(permissions.can_access_task(self.task_a, user=self.worker_b))

	def test_administrator_gets_administrative_participant_access(self):
		self.assertTrue(
			permissions.has_participant_access(
				self.participant_a,
				user="Administrator",
				administrative=True,
			)
		)

	def test_system_manager_gets_administrative_participant_access(self):
		self.assertTrue(
			permissions.has_participant_access(
				self.participant_a,
				user=self.system_manager,
				administrative=True,
			)
		)

	def test_administrative_bypass_does_not_grant_worker_task_action(self):
		self.assertFalse(permissions.can_access_task(self.task_a, user=self.system_manager, administrative=True))

	def test_direct_participant_document_resolves(self):
		plan = frappe.get_doc("Support Plan", self.plan_a)
		self.assertEqual(permissions.resolve_participant("Support Plan", plan), self.participant_a)

	def test_support_task_resolves_through_support_plan(self):
		self.assertEqual(permissions.resolve_participant("Support Task", self.task_a), self.participant_a)

	def test_execution_instance_resolves_through_support_task(self):
		execution = frappe.get_doc(
			{
				"doctype": "Support Task Execution Instance",
				"support_task": self.task_a,
				"scheduled_date": frappe.utils.today(),
				"scheduled_time": "09:00:00",
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(
			permissions.resolve_participant("Support Task Execution Instance", execution),
			self.participant_a,
		)

	def test_delivery_log_resolves_through_execution(self):
		execution = frappe.get_doc(
			{
				"doctype": "Support Task Execution Instance",
				"support_task": self.task_a,
				"scheduled_date": frappe.utils.today(),
				"scheduled_time": "09:00:00",
				"status": "Delivered",
				"executed_by": self.worker_a,
				"actual_execution_time": frappe.utils.now_datetime(),
			}
		).insert(ignore_permissions=True)
		log = frappe.get_doc(
			{
				"doctype": "Support Task Delivery Log",
				"execution_instance": execution.name,
				"delivered_timestamp": frappe.utils.now_datetime(),
				"primary_staff": self.worker_a,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(permissions.resolve_participant("Support Task Delivery Log", log), self.participant_a)

	def test_unknown_doctype_fails_closed(self):
		self.assertIsNone(permissions.resolve_participant("Unknown DocType", "UNKNOWN"))

	def test_missing_or_broken_link_fails_closed(self):
		self.assertIsNone(
			permissions.resolve_participant(
				"Support Task",
				{"doctype": "Support Task", "support_plan": "missing-support-plan"},
			)
		)

	def test_mismatched_declared_doctype_fails_closed(self):
		self.assertIsNone(
			permissions.resolve_participant(
				"Support Task",
				{"doctype": "Support Plan", "name": self.task_a, "support_plan": self.plan_a},
			)
		)

	def test_missing_declared_doctype_fails_closed(self):
		self.assertIsNone(
			permissions.resolve_participant(
				"Support Task",
				{"name": self.task_a, "support_plan": self.plan_a},
			)
		)

	def test_mismatched_task_document_cannot_access_task(self):
		self.assertFalse(
			permissions.can_access_task(
				{"doctype": "Support Plan", "name": self.task_a, "status": "Active"},
				user=self.worker_a,
			)
		)

	def test_spoofed_active_status_does_not_override_stored_paused_task(self):
		paused_task = ensure_r2c1_support_task(self.plan_a, "Paused", status="Paused")
		ensure_r2c1_task_assignment(paused_task, self.worker_a)
		self.assertFalse(
			permissions.can_access_task(
				{
					"doctype": "Support Task",
					"name": paused_task,
					"status": "Active",
					"support_plan": self.plan_a,
				},
				user=self.worker_a,
			)
		)

	def test_spoofed_support_plan_does_not_override_stored_task_participant(self):
		ensure_r2c1_task_assignment(self.task_b, self.worker_a)
		self.assertFalse(
			permissions.can_access_task(
				{
					"doctype": "Support Task",
					"name": self.task_b,
					"status": "Active",
					"support_plan": self.plan_a,
				},
				user=self.worker_a,
			)
		)

	def test_missing_task_action_fails_closed(self):
		self.assertFalse(
			permissions.can_access_task(
				{
					"doctype": "Support Task",
					"name": "missing-support-task",
					"status": "Active",
					"support_plan": self.plan_a,
				},
				user=self.worker_a,
			)
		)

	def test_missing_declared_task_document_cannot_access_task(self):
		self.assertFalse(
			permissions.can_access_task(
				{"name": self.task_a, "status": "Active", "support_plan": self.plan_a},
				user=self.worker_a,
			)
		)

	def test_single_role_string_is_not_split_into_characters(self):
		self.assertTrue(permissions.has_any_role("Support Worker", user=self.worker_a))
		self.assertFalse(permissions.has_any_role("Care Manager", user=self.worker_a))

	def test_cache_helper_uses_only_targeted_user_clear(self):
		with patch.object(frappe, "clear_cache") as clear_cache:
			clear_r2c1_permission_caches()
			clear_cache.assert_not_called()

			clear_r2c1_permission_caches(self.worker_a)
			clear_cache.assert_called_once_with(user=self.worker_a)

	def test_unknown_doctype_resolution_avoids_database_calls(self):
		with (
			patch.object(frappe.db, "get_value", side_effect=AssertionError("unexpected get_value")),
			patch.object(frappe.db, "exists", side_effect=AssertionError("unexpected exists")),
		):
			self.assertIsNone(permissions.resolve_participant("Unknown DocType", "UNKNOWN"))

	def test_mismatched_doctype_resolution_avoids_database_calls(self):
		with (
			patch.object(frappe.db, "get_value", side_effect=AssertionError("unexpected get_value")),
			patch.object(frappe.db, "exists", side_effect=AssertionError("unexpected exists")),
		):
			self.assertIsNone(
				permissions.resolve_participant(
					"Support Task",
					{"doctype": "Support Plan", "name": self.task_a, "support_plan": self.plan_a},
				)
			)

	def test_require_participant_access_raises_when_denied(self):
		self.assertRaises(
			frappe.PermissionError,
			permissions.require_participant_access,
			self.participant_b,
			self.care_manager,
		)

	def test_require_task_action_access_raises_when_denied(self):
		self.assertRaises(
			frappe.PermissionError,
			permissions.require_task_action_access,
			self.task_b,
			self.worker_a,
		)

	def test_require_participant_access_honors_matching_applicable_for(self):
		self.assertTrue(
			permissions.require_participant_access(
				self.participant_a,
				self.scoped_worker,
				applicable_for="Support Task",
			)
		)

	def test_require_participant_access_rejects_mismatched_applicable_for(self):
		self.assertRaises(
			frappe.PermissionError,
			permissions.require_participant_access,
			self.participant_a,
			self.scoped_worker,
			False,
			"Support Plan",
		)

	def test_authorization_checks_do_not_mutate_care_records(self):
		before = frappe.db.count("Support Task")
		permissions.has_participant_access(self.participant_a, user=self.care_manager)
		permissions.can_access_task(self.task_a, user=self.worker_a)
		permissions.resolve_participant("Support Task", self.task_a)
		after = frappe.db.count("Support Task")
		self.assertEqual(after, before)
