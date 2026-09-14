from unittest.mock import patch
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management import permissions
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_task_assignment,
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
		"Medication Event Addendum",
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

	def insert_prn_event_row(self, participant, worker, name_suffix):
		name = f"R3C3-PRN-PICKER-{name_suffix}-{frappe.generate_hash(length=8)}"
		frappe.db.sql(
			"""
			insert into `tabMedication Administration Event`
				(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`,
				 `participant`, `medication_plan`, `medication_plan_item`, `scheduled_datetime`,
				 `actual_datetime`, `worker`, `outcome`, `is_prn_snapshot`)
			values
				(%s, now(), now(), %s, %s, 1, %s, %s, %s, now(), now(), %s, 'Administered', 1)
			""",
			(
				name,
				"Administrator",
				"Administrator",
				participant,
				"R3C3-PRN-PICKER-PLAN",
				"R3C3-PRN-PICKER-ITEM",
				worker,
			),
		)
		return name

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

	def test_hooks_register_exactly_35_query_targets(self):
		import care_management.hooks as hooks

		self.assertEqual(set(hooks.permission_query_conditions), EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertEqual(len(hooks.permission_query_conditions), 35)

	def test_hooks_register_exactly_36_document_targets(self):
		import care_management.hooks as hooks

		self.assertEqual(set(hooks.has_permission), EXPECTED_PROTECTED_PARTICIPANT_DOCTYPES | {"File"})
		self.assertEqual(len(hooks.has_permission), 36)

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
		self.assertEqual(len(permissions.PROTECTED_PARTICIPANT_DOCTYPES), 35)
		self.assertIn("Medication Administration Event", permissions.PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertIn("Medication Event Addendum", permissions.PROTECTED_PARTICIPANT_DOCTYPES)
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

	def test_medication_log_participant_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"medication_administration_log",
				"medication_administration_log.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.medication_administration_log.medication_administration_log.search_medication_log_participants",
			script,
		)

	def test_medication_log_participant_link_query_returns_only_applicable_grant(self):
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Medication Administration Log",
		)
		frappe.set_user(self.care_manager)
		rows = permissions.search_medication_log_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_medication_event_participant_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"medication_administration_event",
				"medication_administration_event.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_participants",
			script,
		)

	def test_medication_event_participant_link_query_returns_only_applicable_worker_grant(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication Administration Event",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_medication_event_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_medication_event_plan_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"medication_administration_event",
				"medication_administration_event.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_plans",
			script,
		)

	def test_medication_log_participant_search_does_not_grant_support_worker_lookup(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication Administration Log",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_medication_log_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual(rows, [])

	def test_medication_event_support_task_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"medication_administration_event",
				"medication_administration_event.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_support_tasks",
			script,
		)

	def test_medication_event_support_task_query_returns_only_assigned_applicable_task(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication Administration Event",
		)
		ensure_r2c1_task_assignment(self.task_a, self.worker)
		task_doc = frappe.get_doc("Support Task", self.task_a)
		task_doc.source_doctype = "Medication Administration Log"
		task_doc.save(ignore_permissions=True)
		frappe.set_user(self.worker)
		rows = permissions.search_medication_event_support_tasks(
			"Support Task",
			"R2C1 Task R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.task_a})

	def test_medication_event_plan_query_returns_only_assigned_applicable_plan(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication Administration Event",
		)
		ensure_r2c1_task_assignment(self.task_a, self.worker)
		plan_a = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		plan_b = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_b,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Medication Administration Log", plan_a.name, "plan_status", "Active", update_modified=False)
		frappe.db.set_value("Medication Administration Log", plan_b.name, "plan_status", "Active", update_modified=False)
		task_doc = frappe.get_doc("Support Task", self.task_a)
		task_doc.source_doctype = "Medication Administration Log"
		task_doc.source_docname = plan_a.name
		task_doc.save(ignore_permissions=True)
		frappe.set_user(self.worker)
		rows = permissions.search_medication_event_plans(
			"Medication Administration Log",
			"MED-LOG",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {plan_a.name})
		self.assertNotIn(plan_b.name, {row[0] for row in rows})

	def test_medication_prn_review_links_use_scoped_queries(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"medication_prn_effectiveness_review",
				"medication_prn_effectiveness_review.js",
			)
		).read_text()
		for method in (
			"search_medication_prn_review_participants",
			"search_medication_prn_review_events",
			"search_medication_prn_review_plans",
		):
			self.assertIn(
				f"care_management.care_management.doctype.medication_prn_effectiveness_review.medication_prn_effectiveness_review.{method}",
				script,
			)

	def test_medication_prn_review_participant_query_returns_only_applicable_grant(self):
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Medication PRN Effectiveness Review",
		)
		frappe.set_user(self.care_manager)
		rows = permissions.search_medication_prn_review_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_medication_prn_review_plan_query_returns_only_applicable_grant(self):
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Medication PRN Effectiveness Review",
		)
		plan_a = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		plan_b = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_b,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Medication Administration Log", plan_a.name, "plan_status", "Active", update_modified=False)
		frappe.db.set_value("Medication Administration Log", plan_b.name, "plan_status", "Active", update_modified=False)
		frappe.set_user(self.care_manager)
		rows = permissions.search_medication_prn_review_plans(
			"Medication Administration Log",
			"MED-LOG",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {plan_a.name})
		self.assertNotIn(plan_b.name, {row[0] for row in rows})

	def test_search_query_shims_use_standard_frappe_sanitizer(self):
		from care_management.care_management.doctype.controlled_medication_transaction import (
			controlled_medication_transaction,
		)
		from care_management.care_management.doctype.discarded_medication_register import (
			discarded_medication_register,
		)
		from care_management.care_management.doctype.incident import incident
		from care_management.care_management.doctype.medication_administration_event import (
			medication_administration_event,
		)
		from care_management.care_management.doctype.medication_administration_log import (
			medication_administration_log,
		)
		from care_management.care_management.doctype.medication_prn_effectiveness_review import (
			medication_prn_effectiveness_review,
		)
		from care_management.care_management.doctype.participant_drug_count import participant_drug_count
		from care_management.care_management.doctype.shift_medication_check import shift_medication_check

		for method in (
			medication_administration_log.search_medication_log_participants,
			medication_administration_event.search_medication_event_participants,
			medication_administration_event.search_medication_event_plans,
			medication_administration_event.search_medication_event_support_tasks,
			medication_prn_effectiveness_review.search_medication_prn_review_participants,
			medication_prn_effectiveness_review.search_medication_prn_review_events,
			medication_prn_effectiveness_review.search_medication_prn_review_plans,
			controlled_medication_transaction.search_controlled_transaction_participants,
			controlled_medication_transaction.search_controlled_transaction_plans,
			participant_drug_count.search_participant_drug_count_participants,
			shift_medication_check.search_shift_medication_check_participants,
			shift_medication_check.search_shift_medication_check_reconciliations,
			discarded_medication_register.search_discarded_medication_participants,
			incident.search_incident_participants,
		):
			self.assertTrue(hasattr(method, "__wrapped__"), method.__name__)

	def test_search_query_endpoint_denials_fail_closed(self):
		from care_management.care_management.doctype.medication_administration_log import (
			medication_administration_log,
		)

		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication Administration Log",
		)
		frappe.set_user("Guest")
		self.assertEqual(
			medication_administration_log.search_medication_log_participants(
				"Participant Profile",
				"R2C1 Participant R2C2",
				"name",
				0,
				20,
			),
			[],
		)
		frappe.set_user(self.worker)
		self.assertEqual(
			medication_administration_log.search_medication_log_participants(
				"Participant Profile",
				"R2C1 Participant R2C2",
				"name",
				0,
				20,
			),
			[],
		)
		frappe.set_user(self.unmapped_user)
		self.assertEqual(
			medication_administration_log.search_medication_log_participants(
				"Participant Profile",
				"R2C1 Participant R2C2",
				"name",
				0,
				20,
			),
			[],
		)
		frappe.set_user(self.care_manager)
		self.assertEqual(
			medication_administration_log.search_medication_log_participants(
				"User",
				"R2C1 Participant R2C2",
				"name",
				0,
				20,
			),
			[],
		)
		self.assertRaises(
			frappe.DataError,
			medication_administration_log.search_medication_log_participants,
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name desc",
			0,
			20,
		)
		self.assertEqual(
			list(permissions.search_medication_log_participants(
				"Participant Profile",
				"R2C1 Participant R2C2",
				"name",
				"bad",
				20,
			)),
			[],
		)
		self.assertEqual(
			list(medication_administration_log.search_medication_log_participants(
				"Participant Profile",
				self.participant_b,
				"name",
				0,
				20,
			)),
			[],
		)

	def test_support_worker_prn_review_event_picker_returns_only_own_prn_events(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Medication PRN Effectiveness Review",
		)
		ensure_r2c1_user_permission(
			self.other_worker,
			self.participant_a,
			applicable_for="Medication PRN Effectiveness Review",
		)
		own_event = self.insert_prn_event_row(self.participant_a, self.worker, "OWN")
		other_worker_event = self.insert_prn_event_row(self.participant_a, self.other_worker, "OTHER")
		cross_participant_event = self.insert_prn_event_row(self.participant_b, self.worker, "CROSS")
		frappe.set_user(self.worker)
		rows = permissions.search_medication_prn_review_events(
			"Medication Administration Event",
			"R3C3-PRN-PICKER",
			"name",
			0,
			20,
		)
		names = {row[0] for row in rows}
		self.assertEqual(names, {own_event})
		self.assertNotIn(other_worker_event, names)
		self.assertNotIn(cross_participant_event, names)

	def test_manager_prn_review_event_picker_remains_participant_scoped(self):
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Medication PRN Effectiveness Review",
		)
		worker_event = self.insert_prn_event_row(self.participant_a, self.worker, "MANAGER-WORKER")
		other_worker_event = self.insert_prn_event_row(self.participant_a, self.other_worker, "MANAGER-OTHER")
		cross_participant_event = self.insert_prn_event_row(self.participant_b, self.other_worker, "MANAGER-CROSS")
		frappe.set_user(self.care_manager)
		rows = permissions.search_medication_prn_review_events(
			"Medication Administration Event",
			"R3C3-PRN-PICKER",
			"name",
			0,
			20,
		)
		names = {row[0] for row in rows}
		self.assertEqual(names, {worker_event, other_worker_event})
		self.assertNotIn(cross_participant_event, names)

	def test_controlled_transaction_links_use_scoped_queries(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"controlled_medication_transaction",
				"controlled_medication_transaction.js",
			)
		).read_text()
		for method in (
			"search_controlled_transaction_participants",
			"search_controlled_transaction_plans",
		):
			self.assertIn(
				f"care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction.{method}",
				script,
			)

	def test_controlled_transaction_client_previews_server_derived_mandatory_fields(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"controlled_medication_transaction",
				"controlled_medication_transaction.js",
			)
		).read_text()
		for fieldname in (
			"balance_before",
			"balance_after",
			"actor",
			"source_doctype",
			"source_docname",
			"source_action",
			"source_key",
		):
			self.assertIn(f'"{fieldname}"', script)
		self.assertIn("client-preview", script)
		self.assertIn("frm.is_new()", script)

	def test_controlled_transaction_participant_query_returns_only_applicable_grant(self):
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Controlled Medication Transaction",
		)
		frappe.set_user(self.care_manager)
		rows = permissions.search_controlled_transaction_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_participant_drug_count_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"participant_drug_count",
				"participant_drug_count.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.participant_drug_count.participant_drug_count.search_participant_drug_count_participants",
			script,
		)

	def test_participant_drug_count_participant_query_returns_only_applicable_grant(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Participant Drug Count",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_participant_drug_count_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_shift_medication_check_participant_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"shift_medication_check",
				"shift_medication_check.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.shift_medication_check.shift_medication_check.search_shift_medication_check_participants",
			script,
		)

	def test_shift_medication_check_participant_query_returns_only_applicable_worker_grant(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Shift Medication Check",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_shift_medication_check_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_shift_medication_check_reconciliation_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"shift_medication_check",
				"shift_medication_check.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.shift_medication_check.shift_medication_check.search_shift_medication_check_reconciliations",
			script,
		)
		self.assertIn("participant: frm.doc.participant", script)

	def test_shift_medication_check_reconciliation_query_returns_only_same_participant_reconciled_count(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Shift Medication Check",
		)
		plan_a = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		plan_a.append(
			"medication_items",
			{
				"medication_name": "R2C2 Shift Check Count A",
				"dosage": "1 tablet",
				"route": "Oral",
				"time_slot": "6 AM",
				"medication_form": "Tablet",
				"strength": "1 tablet",
				"prescribed_dose": "1",
				"dose_unit": "tablet",
				"scheduled_time": "06:00:00",
				"frequency": "Daily",
				"indication": "Shift check reconciliation fixture",
				"is_active": 1,
			},
		)
		plan_a.save(ignore_permissions=True)
		plan_b = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_b,
				"plan_status": "Draft",
				"effective_from": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		plan_b.append(
			"medication_items",
			{
				"medication_name": "R2C2 Shift Check Count B",
				"dosage": "1 tablet",
				"route": "Oral",
				"time_slot": "6 AM",
				"medication_form": "Tablet",
				"strength": "1 tablet",
				"prescribed_dose": "1",
				"dose_unit": "tablet",
				"scheduled_time": "06:00:00",
				"frequency": "Daily",
				"indication": "Shift check reconciliation fixture",
				"is_active": 1,
			},
		)
		plan_b.save(ignore_permissions=True)
		count_a = frappe.get_doc(
			{
				"doctype": "Participant Drug Count",
				"participant": self.participant_a,
				"webster_pak_type": "Schedule 8 (S8)",
				"schedule_8_details": "R2C2 same participant reconciliation",
				"medication_plan_item": plan_a.medication_items[0].name,
				"observed_balance": "0",
				"drug_count_entries": [
					{
						"date": frappe.utils.today(),
						"staff_name": self.worker,
						"expected_count": 0,
						"actual_count": 0,
						"actual_end_of_shift_count": 0,
						"staff_signature": self.worker,
					}
				],
			}
		).insert(ignore_permissions=True)
		count_a.submit()
		count_b = frappe.get_doc(
			{
				"doctype": "Participant Drug Count",
				"participant": self.participant_b,
				"webster_pak_type": "Schedule 8 (S8)",
				"schedule_8_details": "R2C2 cross participant reconciliation",
				"medication_plan_item": plan_b.medication_items[0].name,
				"observed_balance": "0",
				"drug_count_entries": [
					{
						"date": frappe.utils.today(),
						"staff_name": self.other_worker,
						"expected_count": 0,
						"actual_count": 0,
						"actual_end_of_shift_count": 0,
						"staff_signature": self.other_worker,
					}
				],
			}
		).insert(ignore_permissions=True)
		count_b.submit()
		frappe.set_user(self.worker)
		rows = permissions.search_shift_medication_check_reconciliations(
			"Participant Drug Count",
			"DRUG-CNT",
			"name",
			0,
			20,
			filters={"participant": self.participant_a},
		)
		self.assertIn(count_a.name, {row[0] for row in rows})
		self.assertNotIn(count_b.name, {row[0] for row in rows})

	def test_discarded_medication_participant_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"discarded_medication_register",
				"discarded_medication_register.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.discarded_medication_register.discarded_medication_register.search_discarded_medication_participants",
			script,
		)

	def test_discarded_medication_participant_query_returns_only_applicable_worker_grant(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Discarded Medication Register",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_discarded_medication_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

	def test_incident_participant_link_uses_scoped_query(self):
		script = Path(
			frappe.get_app_path(
				"care_management",
				"care_management",
				"doctype",
				"incident",
				"incident.js",
			)
		).read_text()
		self.assertIn(
			"care_management.care_management.doctype.incident.incident.search_incident_participants",
			script,
		)

	def test_incident_participant_query_returns_only_applicable_worker_grant(self):
		ensure_r2c1_user_permission(
			self.worker,
			self.participant_a,
			applicable_for="Incident",
		)
		frappe.set_user(self.worker)
		rows = permissions.search_incident_participants(
			"Participant Profile",
			"R2C1 Participant R2C2",
			"name",
			0,
			20,
		)
		self.assertEqual({row[0] for row in rows}, {self.participant_a})

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
