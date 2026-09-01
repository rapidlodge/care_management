from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management import permissions
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_support_task,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)


EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES = frozenset(
	{
		"Appointment Schedule",
		"Custom Care Plan",
		"Daily Bowel Record Chart",
		"Daily Cleaning Task Checklist",
		"Daily Food Diary",
		"Daily Shift Task Checklist",
		"Discarded Medication Register",
		"Epilepsy Management Plan",
		"Falls Risk Plan",
		"Fluid Intake Output Chart",
		"Hospital Support Plan",
		"Incident",
		"Manager Follow-up",
		"Medical Report Summary",
		"Medication Administration Event",
		"Medication Administration Log",
		"Medication PRN Effectiveness Review",
		"Controlled Medication Transaction",
		"Mood Tracker",
		"Participant Drug Count",
		"Participant Profile",
		"Seizure Chart",
		"Shift Handover Item",
		"Shift Medication Check",
		"Shower Chart",
		"Skin Integrity Form",
		"Sleep Tracker",
		"Support Plan",
		"Support Task",
		"Support Task Delivery Log",
		"Support Task Execution Instance",
		"Support Task Missed Log",
		"Weekly Exercise Record",
		"Weekly Meal Planner",
	}
)


class TestParticipantPermissionHooks(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R2C2 A", "2234567890")
		self.participant_b = ensure_r2c1_participant("R2C2 B", "22345678901")
		self.plan_a = ensure_r2c1_support_plan(self.participant_a, "R2C2 A")
		self.plan_b = ensure_r2c1_support_plan(self.participant_b, "R2C2 B")
		self.task_a = ensure_r2c1_support_task(self.plan_a, "R2C2 A")
		self.task_b = ensure_r2c1_support_task(self.plan_b, "R2C2 B")
		self.care_manager = ensure_r2c1_user("R2C2 Care Manager", ["Care Manager"])
		self.coordinator = ensure_r2c1_user("R2C2 Coordinator", ["Support Coordinator"])
		self.worker = ensure_r2c1_user("R2C2 Worker", ["Support Worker"])
		self.other_worker = ensure_r2c1_user("R2C2 Other Worker", ["Support Worker"])
		self.unmapped_user = ensure_r2c1_user("R2C2 Unmapped", ["Care Manager"])
		self.system_manager = ensure_r2c1_user("R2C2 System Manager", ["System Manager"])
		ensure_r2c1_user_permission(self.care_manager, self.participant_a)
		ensure_r2c1_user_permission(self.coordinator, self.participant_a)
		ensure_r2c1_user_permission(self.worker, self.participant_a)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def assert_document_allowed(self, doctype, name, user):
		doc = frappe.get_doc(doctype, name)
		self.assertTrue(permissions.has_participant_document_permission(doc, "read", user))

	def assert_document_denied(self, doctype, name, user):
		doc = frappe.get_doc(doctype, name)
		self.assertFalse(permissions.has_participant_document_permission(doc, "read", user))

	def insert_execution(self, task, status="Pending"):
		values = {
			"doctype": "Support Task Execution Instance",
			"support_task": task,
			"scheduled_date": frappe.utils.today(),
			"scheduled_time": "09:00:00",
			"status": status,
		}
		if status == "Delivered":
			values.update(
				{
					"executed_by": self.worker,
					"actual_execution_time": frappe.utils.now_datetime(),
				}
			)
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def insert_delivery_log(self, execution):
		return frappe.get_doc(
			{
				"doctype": "Support Task Delivery Log",
				"execution_instance": execution.name,
				"delivered_timestamp": frappe.utils.now_datetime(),
				"primary_staff": self.worker,
			}
		).insert(ignore_permissions=True)

	def insert_missed_log(self, execution):
		return frappe.get_doc(
			{
				"doctype": "Support Task Missed Log",
				"execution_instance": execution.name,
				"missed_timestamp": frappe.utils.now_datetime(),
				"logged_by_staff": self.worker,
				"reason_category": "Other",
			}
		).insert(ignore_permissions=True)

	def assert_real_get_list_returns_only_granted(self, doctype, names):
		def get_role_permissions(doctype_meta, user=None, is_owner=None, debug=False):
			return frappe._dict(
				{
					"select": 1,
					"read": 1,
					"write": 0,
					"create": 0,
					"delete": 0,
					"submit": 0,
					"cancel": 0,
					"amend": 0,
					"print": 1,
					"email": 0,
					"report": 1,
					"import": 0,
					"export": 0,
					"share": 0,
					"if_owner": {},
					"has_if_owner_enabled": False,
				}
			)

		frappe.set_user(self.care_manager)
		with patch("frappe.permissions.get_role_permissions", side_effect=get_role_permissions):
			rows = frappe.get_list(
				doctype,
				fields=["name"],
				filters={"name": ["in", names]},
				limit=50,
			)
		self.assertEqual({row.name for row in rows}, {names[0]})

	def test_hooks_register_exactly_34_query_targets(self):
		import care_management.hooks as hooks

		self.assertEqual(set(hooks.permission_query_conditions), EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertEqual(len(hooks.permission_query_conditions), 34)

	def test_hooks_register_exactly_34_document_targets(self):
		import care_management.hooks as hooks

		self.assertEqual(set(hooks.has_permission), EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertEqual(len(hooks.has_permission), 34)

	def test_no_wildcard_permission_hooks_are_registered(self):
		import care_management.hooks as hooks

		self.assertNotIn("*", hooks.permission_query_conditions)
		self.assertNotIn("*", hooks.has_permission)

	def test_no_child_table_permission_hooks_are_registered(self):
		import care_management.hooks as hooks

		self.assertFalse(set(hooks.permission_query_conditions).intersection(permissions.CHILD_PARTICIPANT_PARENTFIELDS))
		self.assertFalse(set(hooks.has_permission).intersection(permissions.CHILD_PARTICIPANT_PARENTFIELDS))

	def test_docshare_guard_is_registered(self):
		import care_management.hooks as hooks

		self.assertEqual(
			hooks.doc_events["DocShare"]["validate"],
			"care_management.care_management.permissions.validate_participant_docshare",
		)

	def test_docshare_guard_is_registered_once(self):
		import care_management.hooks as hooks

		self.assertEqual(set(hooks.doc_events["DocShare"]), {"validate"})

	def test_protected_doctype_inventory_is_exact(self):
		self.assertEqual(permissions.PROTECTED_PARTICIPANT_DOCTYPES, EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertEqual(len(permissions.PROTECTED_PARTICIPANT_DOCTYPES), 34)
		self.assertIn("Medication Administration Event", permissions.PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertNotIn("Medication Competency", permissions.PROTECTED_PARTICIPANT_DOCTYPES)

	def test_participant_profile_document_allowed_by_grant(self):
		self.assert_document_allowed("Participant Profile", self.participant_a, self.care_manager)

	def test_participant_profile_document_denies_cross_participant(self):
		self.assert_document_denied("Participant Profile", self.participant_b, self.care_manager)

	def test_support_plan_document_allowed_by_grant(self):
		self.assert_document_allowed("Support Plan", self.plan_a, self.care_manager)

	def test_support_plan_document_denies_cross_participant(self):
		self.assert_document_denied("Support Plan", self.plan_b, self.care_manager)

	def test_support_task_document_allowed_through_plan(self):
		self.assert_document_allowed("Support Task", self.task_a, self.care_manager)

	def test_support_task_document_denies_cross_participant(self):
		self.assert_document_denied("Support Task", self.task_b, self.care_manager)

	def test_support_coordinator_document_allowed_by_grant(self):
		self.assert_document_allowed("Support Plan", self.plan_a, self.coordinator)

	def test_support_coordinator_cross_participant_denied(self):
		self.assert_document_denied("Support Plan", self.plan_b, self.coordinator)

	def test_guest_document_access_denied(self):
		self.assert_document_denied("Support Plan", self.plan_a, "Guest")

	def test_unmapped_user_document_access_denied(self):
		self.assert_document_denied("Support Plan", self.plan_a, self.unmapped_user)

	def test_support_worker_standard_document_access_denied(self):
		self.assert_document_denied("Support Plan", self.plan_a, self.worker)

	def test_administrator_document_bypass_allowed(self):
		self.assert_document_allowed("Support Plan", self.plan_a, "Administrator")

	def test_system_manager_document_bypass_allowed(self):
		self.assert_document_allowed("Support Plan", self.plan_a, self.system_manager)

	def test_system_manager_write_bypass_is_preserved(self):
		doc = frappe.get_doc("Participant Profile", self.participant_a)
		self.assertTrue(doc.has_permission("write", user=self.system_manager))

	def test_support_coordinator_write_access_is_preserved(self):
		doc = frappe.get_doc("Participant Profile", self.participant_a)
		self.assertTrue(doc.has_permission("write", user=self.coordinator))

	def test_support_coordinator_cross_participant_write_is_denied(self):
		doc = frappe.get_doc("Participant Profile", self.participant_b)
		self.assertFalse(doc.has_permission("write", user=self.coordinator))

	def test_unknown_record_fails_closed(self):
		doc = frappe._dict({"doctype": "Support Plan", "name": "missing-r2c2-plan"})
		self.assertFalse(permissions.has_participant_document_permission(doc, "read", self.care_manager))

	def test_unknown_doctype_fails_closed(self):
		doc = frappe._dict({"doctype": "Unknown DocType", "name": "UNKNOWN"})
		self.assertFalse(permissions.has_participant_document_permission(doc, "read", self.care_manager))

	def test_scoped_write_permission_is_allowed(self):
		doc = frappe.get_doc("Support Plan", self.plan_a)
		self.assertTrue(permissions.has_participant_document_permission(doc, "write", self.care_manager))

	def test_real_frappe_document_hook_is_exercised(self):
		doc = frappe.get_doc("Participant Profile", self.participant_a)
		self.assertTrue(doc.has_permission("write", user=self.care_manager))

	def test_real_frappe_document_hook_denies_cross_participant(self):
		doc = frappe.get_doc("Participant Profile", self.participant_b)
		self.assertFalse(doc.has_permission("write", user=self.care_manager))

	def test_real_frappe_get_list_is_filtered_by_participant_grant(self):
		frappe.set_user(self.care_manager)
		rows = frappe.get_list(
			"Participant Profile",
			fields=["name"],
			order_by="name asc",
			limit=50,
		)
		names = {row.name for row in rows}
		self.assertIn(self.participant_a, names)
		self.assertNotIn(self.participant_b, names)

	def test_real_frappe_get_list_denies_caller_filter_widening(self):
		frappe.set_user(self.care_manager)
		rows = frappe.get_list(
			"Participant Profile",
			fields=["name"],
			filters={"name": ["in", [self.participant_a, self.participant_b]]},
			limit=50,
		)
		self.assertEqual({row.name for row in rows}, {self.participant_a})

	def test_real_frappe_get_list_denies_or_filter_widening(self):
		frappe.set_user(self.care_manager)
		rows = frappe.get_list(
			"Participant Profile",
			fields=["name"],
			or_filters={"name": ["in", [self.participant_a, self.participant_b]]},
			limit=50,
		)
		self.assertEqual({row.name for row in rows}, {self.participant_a})

	def test_real_frappe_get_list_support_coordinator_is_filtered(self):
		frappe.set_user(self.coordinator)
		rows = frappe.get_list("Participant Profile", fields=["name"], limit=50)
		names = {row.name for row in rows}
		self.assertIn(self.participant_a, names)
		self.assertNotIn(self.participant_b, names)

	def test_real_frappe_get_list_unmapped_user_returns_no_rows(self):
		frappe.set_user(self.unmapped_user)
		rows = frappe.get_list("Participant Profile", fields=["name"], limit=50)
		self.assertEqual(rows, [])

	def test_real_frappe_get_list_support_worker_has_no_standard_access(self):
		frappe.set_user(self.worker)
		self.assertRaises(frappe.PermissionError, frappe.get_list, "Participant Profile", fields=["name"], limit=50)

	def test_real_frappe_get_list_administrator_query_bypass_is_unrestricted(self):
		frappe.set_user("Administrator")
		rows = frappe.get_list(
			"Participant Profile",
			fields=["name"],
			filters={"name": ["in", [self.participant_a, self.participant_b]]},
			limit=50,
		)
		self.assertEqual({row.name for row in rows}, {self.participant_a, self.participant_b})

	def test_real_frappe_get_list_system_manager_query_bypass_is_unrestricted(self):
		frappe.set_user(self.system_manager)
		rows = frappe.get_list(
			"Participant Profile",
			fields=["name"],
			filters={"name": ["in", [self.participant_a, self.participant_b]]},
			limit=50,
		)
		self.assertEqual({row.name for row in rows}, {self.participant_a, self.participant_b})

	def test_care_manager_participant_profile_create_policy(self):
		doc = frappe.new_doc("Participant Profile")
		doc.participant = "R2C2 Unsaved Participant"
		self.assertTrue(permissions.has_participant_document_permission(doc, "create", self.care_manager))

	def test_real_direct_support_plan_query_shape_is_filtered(self):
		self.assert_real_get_list_returns_only_granted("Support Plan", [self.plan_a, self.plan_b])

	def test_real_support_task_query_shape_is_filtered(self):
		self.assert_real_get_list_returns_only_granted("Support Task", [self.task_a, self.task_b])

	def test_real_execution_query_shape_is_filtered(self):
		execution_a = self.insert_execution(self.task_a)
		execution_b = self.insert_execution(self.task_b)
		self.assert_real_get_list_returns_only_granted(
			"Support Task Execution Instance",
			[execution_a.name, execution_b.name],
		)

	def test_real_delivery_log_query_shape_is_filtered(self):
		execution_a = self.insert_execution(self.task_a, status="Delivered")
		execution_b = self.insert_execution(self.task_b, status="Delivered")
		log_a = self.insert_delivery_log(execution_a)
		log_b = self.insert_delivery_log(execution_b)
		self.assert_real_get_list_returns_only_granted("Support Task Delivery Log", [log_a.name, log_b.name])

	def test_real_missed_log_query_shape_is_filtered(self):
		execution_a = self.insert_execution(self.task_a)
		execution_b = self.insert_execution(self.task_b)
		log_a = self.insert_missed_log(execution_a)
		log_b = self.insert_missed_log(execution_b)
		self.assert_real_get_list_returns_only_granted("Support Task Missed Log", [log_a.name, log_b.name])

	def test_query_hook_accepts_frappe_canonical_signature(self):
		method_name = permissions.permission_query_condition_method_name("Participant Profile")
		condition = getattr(permissions, method_name)(self.care_manager, doctype="Participant Profile")
		self.assertIn(self.participant_a, condition)

	def test_bound_query_wrapper_mismatch_fails_closed_without_grant_lookup(self):
		method_name = permissions.permission_query_condition_method_name("Participant Profile")
		with patch.object(
			permissions,
			"get_user_participant_grants",
			side_effect=AssertionError("unexpected grant lookup"),
		):
			self.assertEqual(getattr(permissions, method_name)(self.care_manager, doctype="Support Plan"), "1=0")

	def test_document_hook_accepts_frappe_canonical_signature(self):
		doc = frappe.get_doc("Participant Profile", self.participant_a)
		self.assertTrue(
			permissions.has_participant_document_permission(
				doc=doc,
				ptype="write",
				user=self.care_manager,
				debug=True,
			)
		)

	def test_query_condition_for_granted_participant_profile_mentions_only_grant(self):
		condition = permissions.get_participant_permission_query_conditions(
			"Participant Profile",
			user=self.care_manager,
		)
		self.assertIn(self.participant_a, condition)
		self.assertNotIn(self.participant_b, condition)

	def test_query_condition_for_support_plan_uses_participant_field(self):
		condition = permissions.get_participant_permission_query_conditions("Support Plan", user=self.care_manager)
		self.assertIn("`tabSupport Plan`.`participant`", condition)
		self.assertIn(self.participant_a, condition)

	def test_query_condition_for_support_task_uses_support_plan_join(self):
		condition = permissions.get_participant_permission_query_conditions("Support Task", user=self.care_manager)
		self.assertIn("`tabSupport Plan`", condition)
		self.assertIn("`tabSupport Task`.`support_plan`", condition)

	def test_query_condition_for_guest_is_fail_closed(self):
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user="Guest"),
			"1=0",
		)

	def test_query_condition_for_support_worker_is_fail_closed(self):
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user=self.worker),
			"1=0",
		)
		condition = permissions.get_participant_permission_query_conditions(
			"Medication Administration Event",
			user=self.worker,
		)
		self.assertIn("`tabMedication Administration Event`.`participant`", condition)
		self.assertIn(self.participant_a, condition)
		self.assertNotIn(self.participant_b, condition)

	def test_query_condition_for_unmapped_user_is_fail_closed(self):
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user=self.unmapped_user),
			"1=0",
		)

	def test_administrator_query_bypass(self):
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user="Administrator"),
			"",
		)

	def test_system_manager_query_bypass(self):
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user=self.system_manager),
			"",
		)

	def test_applicable_for_scope_is_enforced_for_query_conditions(self):
		scoped = ensure_r2c1_user("R2C2 Scoped Plan", ["Care Manager"])
		ensure_r2c1_user_permission(scoped, self.participant_a, applicable_for="Support Plan")
		self.assertNotEqual(
			permissions.get_participant_permission_query_conditions("Support Plan", user=scoped),
			"1=0",
		)
		self.assertEqual(
			permissions.get_participant_permission_query_conditions("Support Task", user=scoped),
			"1=0",
		)

	def test_caller_filter_widening_is_denied_by_hook_condition(self):
		condition = permissions.get_participant_permission_query_conditions("Support Plan", user=self.care_manager)
		self.assertIn(self.participant_a, condition)
		self.assertNotIn(self.participant_b, condition)

	def test_explicit_docshare_widening_is_denied_by_document_hook(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_b,
				"user": self.care_manager,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)
		self.assert_document_denied("Support Plan", self.plan_b, self.care_manager)

	def test_docshare_for_granted_participant_is_allowed(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": self.care_manager,
				"read": 1,
			}
		)
		self.assertIsNone(permissions.validate_participant_docshare(share))

	def test_docshare_for_support_worker_is_denied(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": self.worker,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_everyone_is_denied(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"everyone": 1,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_blank_recipient_does_not_fall_back_to_session_user(self):
		frappe.set_user("Administrator")
		for value in (None, "", " "):
			share = frappe.get_doc(
				{
					"doctype": "DocShare",
					"share_doctype": "Support Plan",
					"share_name": self.plan_a,
					"everyone": 0,
					"user": value,
					"read": 1,
				}
			)
			self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_guest_recipient_is_denied(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": "Guest",
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_unknown_recipient_is_denied(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": "missing-r2c2-docshare@example.test",
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_disabled_user_is_denied(self):
		disabled_user = ensure_r2c1_user("R2C2 Disabled", ["Care Manager"])
		ensure_r2c1_user_permission(disabled_user, self.participant_a)
		frappe.db.set_value("User", disabled_user, "enabled", 0)
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": disabled_user,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_docshare_website_user_is_denied(self):
		website_user = "r2c1-r2c2-website@example.test"
		if not frappe.db.exists("User", website_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": website_user,
					"first_name": "R2C2 Website",
					"enabled": 1,
					"user_type": "Website User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		ensure_r2c1_user_permission(website_user, self.participant_a)
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": website_user,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, permissions.validate_participant_docshare, share)

	def test_unknown_docshare_doctype_is_ignored(self):
		share = frappe._dict({"share_doctype": "ToDo", "share_name": "x", "user": self.care_manager})
		self.assertIsNone(permissions.validate_participant_docshare(share))

	def test_real_docshare_insert_same_participant_is_allowed(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_a,
				"user": self.care_manager,
				"read": 1,
			}
		).insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("DocShare", share.name))

	def test_real_docshare_insert_cross_participant_is_denied(self):
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Support Plan",
				"share_name": self.plan_b,
				"user": self.care_manager,
				"read": 1,
			}
		)
		self.assertRaises(frappe.PermissionError, share.insert, ignore_permissions=True)

	def test_query_wrapper_exists_for_every_protected_doctype(self):
		for doctype in permissions.PROTECTED_PARTICIPANT_DOCTYPES:
			method_name = permissions.permission_query_condition_method_name(doctype)
			self.assertTrue(hasattr(permissions, method_name), doctype)

	def test_document_hook_does_not_mutate_records(self):
		before = frappe.db.count("Support Plan")
		self.assert_document_allowed("Support Plan", self.plan_a, self.care_manager)
		after = frappe.db.count("Support Plan")
		self.assertEqual(after, before)

	def test_unknown_doctype_query_avoids_database_calls(self):
		with patch.object(frappe.db, "get_value", side_effect=AssertionError("unexpected get_value")):
			self.assertEqual(
				permissions.get_participant_permission_query_conditions("Unknown DocType", user=self.care_manager),
				"1=0",
			)
