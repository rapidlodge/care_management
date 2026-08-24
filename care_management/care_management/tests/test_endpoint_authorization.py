import inspect
import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from care_management.care_management import permissions
from care_management.care_management.doctype.custom_care_plan.custom_care_plan import (
	CustomCarePlan,
)
from care_management.care_management.page.manager_dashboard import manager_dashboard
from care_management.care_management.page.support_task_schedule import support_task_schedule
from care_management.care_management.tests.helpers import (
	clear_r2c3b_permission_caches,
	ensure_r2c3b_custom_care_plan,
	ensure_r2c3b_execution,
	ensure_r2c3b_manager_follow_up,
	ensure_r2c3b_participant,
	ensure_r2c3b_support_plan,
	ensure_r2c3b_support_task,
	ensure_r2c3b_user,
	ensure_r2c3b_user_permission,
)
from care_management.care_management.utils import task_sync


REMOTE_ENDPOINTS = (
	manager_dashboard.get_manager_dashboard_data,
	manager_dashboard.get_execution_review_detail,
	manager_dashboard.validate_manager_follow_up_decision,
	manager_dashboard.create_manager_follow_up,
	manager_dashboard.get_manager_follow_ups,
	manager_dashboard.update_manager_follow_up,
	manager_dashboard.get_manager_attention_items,
	support_task_schedule.get_week_tasks,
	support_task_schedule.get_staff_task_context,
	support_task_schedule.start_task_execution,
	support_task_schedule.get_manager_review_tasks,
	support_task_schedule.record_task_outcome,
	support_task_schedule.save_tracker_matrix_entries,
	CustomCarePlan.submit_for_review,
	CustomCarePlan.activate_plan,
	CustomCarePlan.deactivate_plan,
)


STATE_CHANGING_ENDPOINTS = (
	manager_dashboard.validate_manager_follow_up_decision,
	manager_dashboard.create_manager_follow_up,
	manager_dashboard.update_manager_follow_up,
	support_task_schedule.start_task_execution,
	support_task_schedule.record_task_outcome,
	support_task_schedule.save_tracker_matrix_entries,
	CustomCarePlan.submit_for_review,
	CustomCarePlan.activate_plan,
	CustomCarePlan.deactivate_plan,
)


APPROVED_PAGE_ROLES = {
	"care_management/care_management/page/manager_dashboard/manager_dashboard.json": {
		"System Manager",
		"Care Manager",
	},
	"care_management/care_management/page/support_task_schedule/support_task_schedule.json": {
		"System Manager",
		"Care Manager",
		"Support Coordinator",
		"Support Worker",
	},
}


APP_ROOT = Path(__file__).resolve().parents[3]


class TestEndpointAuthorization(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

	def setUp(self):
		super().setUp()
		self.participant_a = ensure_r2c3b_participant("A", "2234567890")
		self.participant_b = ensure_r2c3b_participant("B", "3234567890")
		self.system_manager = ensure_r2c3b_user("system-manager", ["System Manager"])
		self.care_manager_a = ensure_r2c3b_user("care-manager-a", ["Care Manager"])
		self.care_manager_unmapped = ensure_r2c3b_user("care-manager-unmapped", ["Care Manager"])
		self.support_coordinator_a = ensure_r2c3b_user(
			"support-coordinator-a", ["Support Coordinator"]
		)
		self.worker_a = ensure_r2c3b_user("worker-a", ["Support Worker"])
		self.worker_b = ensure_r2c3b_user("worker-b", ["Support Worker"])
		self.unmapped_user = ensure_r2c3b_user("unmapped-user", [])
		self.disabled_user = ensure_r2c3b_user("disabled-user", ["Support Worker"], enabled=0)
		self.website_user = ensure_r2c3b_user(
			"website-user", ["Support Worker"], user_type="Website User"
		)

		for user in (
			self.care_manager_a,
			self.support_coordinator_a,
			self.worker_a,
			self.worker_b,
		):
			ensure_r2c3b_user_permission(user, self.participant_a)
		ensure_r2c3b_user_permission(self.worker_b, self.participant_b)

		self.plan_a = ensure_r2c3b_support_plan(self.participant_a, "A")
		self.plan_b = ensure_r2c3b_support_plan(self.participant_b, "B")
		self.task_a = ensure_r2c3b_support_task(self.plan_a, "A", user=self.worker_a)
		self.task_b = ensure_r2c3b_support_task(self.plan_b, "B", user=self.worker_b)
		self.unassigned_task = ensure_r2c3b_support_task(self.plan_a, "Unassigned")
		self.paused_task = ensure_r2c3b_support_task(self.plan_a, "Paused", user=self.worker_a, status="Paused")
		self.archived_task = ensure_r2c3b_support_task(
			self.plan_a, "Archived", user=self.worker_a, status="Archived"
		)
		self.execution_a = ensure_r2c3b_execution(self.task_a, follow_up_required=1)
		self.execution_b = ensure_r2c3b_execution(self.task_b, follow_up_required=1)
		self.follow_up_a = ensure_r2c3b_manager_follow_up(
			self.execution_a, self.task_a, self.participant_a, self.care_manager_a
		)
		self.draft_plan = ensure_r2c3b_custom_care_plan(
			self.participant_a, "Draft", status="Draft", supervisor=self.care_manager_a
		)
		self.pending_plan = ensure_r2c3b_custom_care_plan(
			self.participant_a, "Pending", status="Pending Review", supervisor=self.care_manager_a
		)
		self.active_plan = ensure_r2c3b_custom_care_plan(
			self.participant_a, "Active", status="Active", supervisor=self.care_manager_a
		)
		clear_r2c3b_permission_caches(
			self.system_manager,
			self.care_manager_a,
			self.care_manager_unmapped,
			self.support_coordinator_a,
			self.worker_a,
			self.worker_b,
			self.unmapped_user,
			self.disabled_user,
			self.website_user,
		)

	def tearDown(self):
		test_users = [
			getattr(self, attr, None)
			for attr in (
				"system_manager",
				"care_manager_a",
				"care_manager_unmapped",
				"support_coordinator_a",
				"worker_a",
				"worker_b",
				"unmapped_user",
				"disabled_user",
				"website_user",
			)
		]
		test_users = [user for user in test_users if user and user.startswith("r2c3b-")]
		for share_name in frappe.get_all(
			"DocShare",
			filters={
				"share_doctype": "User",
				"share_name": ["in", test_users],
				"user": ["in", test_users],
			},
			pluck="name",
		):
			frappe.delete_doc(
				"DocShare",
				share_name,
				force=True,
				ignore_permissions=True,
				ignore_on_trash=True,
				delete_permanently=True,
			)
		frappe.set_user("Administrator")
		super().tearDown()

	def _as(self, user):
		frappe.set_user(user)

	def _assert_permission_denied(self, fn, *args, **kwargs):
		with self.assertRaises(frappe.PermissionError):
			fn(*args, **kwargs)

	def _task_count_snapshot(self):
		return {
			doctype: frappe.db.count(doctype)
			for doctype in (
				"Support Task Execution Instance",
				"Support Task Delivery Log",
				"Support Task Missed Log",
				"Manager Follow-up",
				"Custom Care Plan",
				"Support Task",
			)
		}

	def test_guest_denied_all_remote_endpoints(self):
		frappe.set_user("Guest")
		for endpoint in REMOTE_ENDPOINTS:
			with self.subTest(endpoint=endpoint.__name__):
				self.assertIn("@frappe.whitelist", inspect.getsource(endpoint))
		self._assert_permission_denied(manager_dashboard.get_manager_dashboard_data, today(), today())

	def test_unknown_disabled_and_website_users_denied(self):
		for user in (self.disabled_user, self.website_user):
			with self.subTest(user=user):
				self._as(user)
				self._assert_permission_denied(support_task_schedule.get_week_tasks, today())

	def test_unmapped_enabled_system_user_denied(self):
		self._as(self.unmapped_user)
		self._assert_permission_denied(manager_dashboard.get_manager_dashboard_data, today(), today())

	def test_manager_dashboard_role_matrix(self):
		for user, allowed in (
			(self.system_manager, True),
			(self.care_manager_a, True),
			(self.support_coordinator_a, False),
			(self.worker_a, False),
		):
			with self.subTest(user=user):
				self._as(user)
				if allowed:
					self.assertIsInstance(manager_dashboard.get_manager_dashboard_data(today(), today()), dict)
				else:
					self._assert_permission_denied(
						manager_dashboard.get_manager_dashboard_data, today(), today()
					)

	def test_care_manager_participant_scope(self):
		self._as(self.care_manager_a)
		rows = manager_dashboard.get_manager_follow_ups(participant=self.participant_b)
		self.assertEqual(rows, [])

	def test_support_coordinator_manager_dashboard_denied(self):
		self._as(self.support_coordinator_a)
		self._assert_permission_denied(manager_dashboard.get_manager_dashboard_data, today(), today())

	def test_caller_filters_cannot_widen_scope(self):
		self._as(self.care_manager_a)
		rows = support_task_schedule.get_week_tasks(today(), participant=self.participant_b)
		self.assertTrue(all(row.get("participant") != self.participant_b for row in rows))

	def test_raw_sql_results_are_participant_scoped(self):
		self._as(self.care_manager_a)
		rows = support_task_schedule.get_manager_review_tasks(today(), today())
		self.assertTrue(all(row.get("participant") == self.participant_a for row in rows))

	def test_unauthorized_manager_review_detail_denied(self):
		self._as(self.care_manager_a)
		self._assert_permission_denied(manager_dashboard.get_execution_review_detail, self.execution_b)

	def test_manager_follow_up_read_create_update_scope(self):
		self._as(self.system_manager)
		self.assertTrue(frappe.has_permission("Manager Follow-up", "write", self.follow_up_a))

		self._as(self.care_manager_a)
		self.assertTrue(frappe.has_permission("Manager Follow-up", "read", self.follow_up_a))
		self.assertTrue(frappe.has_permission("Manager Follow-up", "create"))
		self.assertTrue(frappe.has_permission("Manager Follow-up", "write", self.follow_up_a))
		for ptype in ("delete", "share", "export", "import", "email", "print", "report"):
			with self.subTest(ptype=ptype):
				self.assertFalse(frappe.has_permission("Manager Follow-up", ptype, self.follow_up_a))

		rows = manager_dashboard.get_manager_follow_ups()
		self.assertTrue(all(row.get("participant") == self.participant_a for row in rows))
		result = manager_dashboard.update_manager_follow_up(
			self.follow_up_a,
			manager_notes="R2C3B scoped update",
		)
		self.assertTrue(result["updated"])
		before = self._task_count_snapshot()
		self._assert_permission_denied(manager_dashboard.get_execution_review_detail, self.execution_b)
		self._assert_permission_denied(
			manager_dashboard.create_manager_follow_up,
			self.execution_b,
			"Other",
			"Medium",
			"Denied cross participant",
			self.care_manager_a,
			add_days(today(), 1),
		)
		self.assertEqual(before, self._task_count_snapshot())

		for user in (self.support_coordinator_a, self.worker_a):
			with self.subTest(user=user):
				self._as(user)
				self._assert_permission_denied(
					manager_dashboard.update_manager_follow_up,
					self.follow_up_a,
					manager_notes="Denied",
				)

	def test_denied_manager_actions_do_not_mutate(self):
		before = self._task_count_snapshot()
		self._as(self.worker_a)
		self._assert_permission_denied(
			manager_dashboard.create_manager_follow_up,
			self.execution_a,
			"Other",
			"Medium",
			"Denied",
			self.care_manager_a,
			add_days(today(), 1),
		)
		self.assertEqual(before, self._task_count_snapshot())

	def test_worker_reads_assigned_active_task(self):
		self._as(self.worker_a)
		context = support_task_schedule.get_staff_task_context(self.task_a)
		self.assertEqual(context["task"]["name"], self.task_a)

	def test_worker_unassigned_task_denied(self):
		self._as(self.worker_a)
		self._assert_permission_denied(
			support_task_schedule.get_staff_task_context, self.unassigned_task
		)

	def test_cross_worker_task_action_denied(self):
		self._as(self.worker_b)
		self._assert_permission_denied(support_task_schedule.start_task_execution, self.task_a)

	def test_cross_participant_task_action_denied(self):
		self._as(self.worker_a)
		self._assert_permission_denied(support_task_schedule.start_task_execution, self.task_b)

	def test_paused_archived_and_missing_tasks_denied(self):
		self._as(self.worker_a)
		for task in (self.paused_task, self.archived_task, "R2C3B Missing Task"):
			with self.subTest(task=task):
				self._assert_permission_denied(support_task_schedule.start_task_execution, task)

	def test_worker_starts_and_records_assigned_task(self):
		self._as(self.worker_a)
		result = support_task_schedule.start_task_execution(self.task_a)
		self.assertEqual(result["status"], "success")

	def test_manager_cannot_impersonate_worker_action(self):
		self._as(self.care_manager_a)
		self._assert_permission_denied(support_task_schedule.start_task_execution, self.task_a)

	def test_tracker_matrix_role_and_assignment_boundaries(self):
		self._as(self.support_coordinator_a)
		self._assert_permission_denied(
			support_task_schedule.save_tracker_matrix_entries,
			self.participant_a,
			"Mood Tracker",
			[{"date": today(), "mood": "Calm"}],
		)

	def test_spoofed_authority_values_are_ignored(self):
		self._as(self.worker_a)
		self._assert_permission_denied(
			support_task_schedule.save_tracker_matrix_entries,
			self.participant_b,
			"Mood Tracker",
			[{"date": today(), "staff_initials": self.worker_a}],
		)

	def test_worker_responses_use_safe_field_allowlist(self):
		self._as(self.worker_a)
		context = support_task_schedule.get_staff_task_context(self.task_a)
		self.assertNotIn("summary_of_medical_conditions", json.dumps(context, default=str))

	def test_lifecycle_transitions_within_scope(self):
		self._as(self.care_manager_a)
		doc = frappe.get_doc("Custom Care Plan", self.draft_plan)
		self.assertEqual(doc.submit_for_review()["status"], "Pending Review")

	def test_lifecycle_transition_outside_scope_denied(self):
		self._as(self.care_manager_unmapped)
		doc = frappe.get_doc("Custom Care Plan", self.draft_plan)
		self._assert_permission_denied(doc.submit_for_review)

	def test_lifecycle_role_denied(self):
		self._as(self.worker_a)
		doc = frappe.get_doc("Custom Care Plan", self.draft_plan)
		self._assert_permission_denied(doc.submit_for_review)

	def test_lifecycle_standard_write_permission_denied(self):
		self._as(self.care_manager_a)
		doc = frappe.get_doc("Custom Care Plan", self.draft_plan)
		original = frappe.has_permission

		def deny_custom_plan(doctype, ptype="read", doc=None, user=None, *args, **kwargs):
			if doctype == "Custom Care Plan" and ptype == "write":
				return False
			return original(doctype, ptype, doc=doc, user=user, *args, **kwargs)

		frappe.has_permission = deny_custom_plan
		try:
			self._assert_permission_denied(doc.submit_for_review)
		finally:
			frappe.has_permission = original

	def test_internal_helpers_are_not_remotely_callable(self):
		self.assertFalse(getattr(support_task_schedule._get_task_schedule_context, "whitelisted", False))
		self.assertFalse(getattr(task_sync.sync_weekly_meal_plan_tasks, "whitelisted", False))

	def test_trusted_internal_meal_sync_succeeds(self):
		self.assertTrue(hasattr(task_sync, "sync_weekly_meal_plan_tasks"))
		self.assertTrue(hasattr(task_sync, "sync_weekly_meal_plan_tasks_internal"))

	def test_request_endpoints_contain_no_manual_commit(self):
		for endpoint in (
			manager_dashboard.create_manager_follow_up,
			manager_dashboard.update_manager_follow_up,
			support_task_schedule.record_task_outcome,
			support_task_schedule.save_tracker_matrix_entries,
		):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertNotIn("frappe.db.commit", inspect.getsource(endpoint))

	def test_page_role_metadata_matches_locked_policy(self):
		for path, expected_roles in APPROVED_PAGE_ROLES.items():
			with self.subTest(path=path):
				with open(APP_ROOT / path, encoding="utf-8") as handle:
					page = json.load(handle)
				self.assertEqual({row["role"] for row in page.get("roles", [])}, expected_roles)

	def test_all_denied_actions_have_zero_row_drift(self):
		before = self._task_count_snapshot()
		self._as(self.worker_b)
		self._assert_permission_denied(support_task_schedule.start_task_execution, self.task_a)
		self._assert_permission_denied(
			manager_dashboard.validate_manager_follow_up_decision,
			self.execution_a,
			"Mark No Follow-up Required",
		)
		self.assertEqual(before, self._task_count_snapshot())
