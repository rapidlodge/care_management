import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime, today

from care_management.care_management.services.custom_plan_sync_engine import CustomPlanSyncEngine
from care_management.care_management.tests.helpers import (
    ensure_test_participant,
    ensure_test_support_plan,
)

IGNORE_TEST_RECORD_DEPENDENCIES = [
    "Participant Profile",
    "Support Task",
    "User",
]


class TestCustomCarePlan(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.participant = self._ensure_test_participant()
        self.support_plan = ensure_test_support_plan(self.participant)

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    # care_management/care_management/doctype/custom_care_plan/test_custom_care_plan.py

    def _ensure_test_participant(self):
        return ensure_test_participant()

    def _create_sample_plan(self, plan_name="Test Plan Gardening", status="Draft"):
        plan = frappe.new_doc("Custom Care Plan")
        plan.plan_name = plan_name
        plan.participant = self.participant
        plan.category = "Daily Living"
        plan.status = status
        plan.start_date = today()
        plan.end_date = add_days(today(), 30)
        plan.append("activities", {
            "activity_name": "Water Plants",
            "activity_category": "Daily Living",
            "priority": "Medium",
            "frequency": "Daily",
            "scheduled_time": "08:30:00",
            "expected_duration_minutes": 15,
            "instructions": "Encourage independent watering.",
            "is_active": 1
        })
        plan.append("activities", {
            "activity_name": "Garden Weeding",
            "activity_category": "Daily Living",
            "priority": "Low",
            "frequency": "Weekly",
            "days_of_week": "Mon, Wed",
            "scheduled_time": "10:00:00",
            "expected_duration_minutes": 30,
            "instructions": "Assist with garden tools.",
            "is_active": 1
        })
        plan.insert(ignore_permissions=True)
        return plan

    # -------------------------------------------------------------
    # 1. Validation & Schema Tests
    # -------------------------------------------------------------

    def test_plan_validation_requires_activities(self):
        """A plan cannot be created without at least one activity."""
        plan = frappe.new_doc("Custom Care Plan")
        plan.plan_name = "Test Plan Empty"
        plan.participant = self.participant
        plan.category = "Daily Living"
        plan.start_date = today()
        
        self.assertRaises(frappe.ValidationError, plan.insert)

    def test_invalid_date_range(self):
        """End date cannot be prior to start date."""
        plan = frappe.new_doc("Custom Care Plan")
        plan.plan_name = "Test Plan Dates"
        plan.participant = self.participant
        plan.category = "Daily Living"
        plan.start_date = today()
        plan.end_date = add_days(today(), -5)
        plan.append("activities", {
            "activity_name": "Check Routine",
            "frequency": "Daily",
            "scheduled_time": "09:00:00",
            "expected_duration_minutes": 10,
            "instructions": "Check routine"
        })
        self.assertRaises(frappe.ValidationError, plan.insert)

    def test_weekly_frequency_requires_days_of_week(self):
        """Weekly activities must specify days_of_week."""
        plan = frappe.new_doc("Custom Care Plan")
        plan.plan_name = "Test Plan Weekly Invalid"
        plan.participant = self.participant
        plan.category = "Daily Living"
        plan.start_date = today()
        plan.append("activities", {
            "activity_name": "Clean Tools",
            "frequency": "Weekly",
            "days_of_week": "",
            "scheduled_time": "10:00:00",
            "expected_duration_minutes": 20,
            "instructions": "Wash tools"
        })
        self.assertRaises(frappe.ValidationError, plan.insert)

    # -------------------------------------------------------------
    # 2. Lifecycle & State Machine Tests
    # -------------------------------------------------------------

    def test_submit_for_review_transition(self):
        """Draft plans can move to Pending Review."""
        plan = self._create_sample_plan(plan_name="Test Plan Review")
        self.assertEqual(plan.status, "Draft")
        
        plan.submit_for_review()
        self.assertEqual(plan.status, "Pending Review")

    def test_activation_generates_tasks_and_rules(self):
        """Activating a plan generates active Support Tasks and Schedule Rules."""
        plan = self._create_sample_plan(plan_name="Test Plan Activation")
        plan.activate_plan()

        self.assertEqual(plan.status, "Active")
        self.assertEqual(plan.activated_by, "Administrator")
        self.assertIsNotNone(plan.activated_on)

        # Check Support Tasks
        tasks = frappe.get_all(
            "Support Task",
            filters={"source_doctype": "Custom Care Plan", "source_docname": plan.name},
            fields=["name", "task_name", "status", "source_row_id"]
        )
        self.assertEqual(len(tasks), 2)
        for t in tasks:
            self.assertEqual(t.status, "Active")

            # Check Schedule Rules
            rules = frappe.get_all(
                "Support Task Schedule Rule",
                filters={
                    "parent": t.name,
                    "parenttype": "Support Task",
                    "parentfield": "schedule_rules",
                },
                fields=["name", "recurrence_type", "scheduled_time"]
            )
            self.assertEqual(len(rules), 1)

    # -------------------------------------------------------------
    # 3. Idempotency Tests
    # -------------------------------------------------------------

    def test_sync_idempotency(self):
        """Repeated synchronization must not create duplicate tasks or rules."""
        plan = self._create_sample_plan(plan_name="Test Plan Idempotent")
        plan.activate_plan()

        # Trigger sync engine multiple times manually
        engine = CustomPlanSyncEngine(plan)
        engine.sync()
        engine.sync()
        plan.save()

        task_count = frappe.db.count("Support Task", {
            "source_doctype": "Custom Care Plan",
            "source_docname": plan.name
        })
        self.assertEqual(task_count, 2)

        task_names = frappe.get_all(
            "Support Task",
            filters={
                "source_doctype": "Custom Care Plan",
                "source_docname": plan.name,
            },
            pluck="name",
        )
        rule_count = frappe.db.count(
            "Support Task Schedule Rule",
            {
                "parent": ["in", task_names],
                "parenttype": "Support Task",
                "parentfield": "schedule_rules",
            },
        )
        self.assertEqual(rule_count, 2)

    # -------------------------------------------------------------
    # 4. Edits to Active Plans & Stale Activity Handling
    # -------------------------------------------------------------

    def test_edit_active_plan_activity_updates_task(self):
        """Modifying an activity on an active plan updates the corresponding task."""
        plan = self._create_sample_plan(plan_name="Test Plan Edit")
        plan.activate_plan()

        # Modify first activity
        plan.activities[0].instructions = "Updated: Ensure gloves are worn."
        plan.activities[0].expected_duration_minutes = 25
        plan.save()

        task_name = frappe.db.get_value("Support Task", {
            "source_doctype": "Custom Care Plan",
            "source_docname": plan.name,
            "source_row_id": plan.activities[0].name
        }, "name")

        task = frappe.get_doc("Support Task", task_name)
        self.assertEqual(task.description, "Updated: Ensure gloves are worn.")
        self.assertEqual(task.estimated_duration_mins, 25)

    def test_removing_activity_deactivates_stale_task(self):
        """Removing an activity row pauses its task without deleting history."""
        plan = self._create_sample_plan(plan_name="Test Plan Remove Row")
        plan.activate_plan()

        removed_row_id = plan.activities[1].name
        
        # Keep only the first activity and re-save
        plan.activities = [plan.activities[0]]
        plan.save()

        stale_task = frappe.get_all(
            "Support Task",
            filters={
                "source_doctype": "Custom Care Plan",
                "source_docname": plan.name,
                "source_row_id": removed_row_id
            },
            fields=["name", "status"]
        )
        self.assertEqual(len(stale_task), 1)
        self.assertEqual(stale_task[0].status, "Paused")

        stale_rule_count = frappe.db.count(
            "Support Task Schedule Rule",
            {
                "parent": stale_task[0].name,
                "parenttype": "Support Task",
                "parentfield": "schedule_rules",
            },
        )
        self.assertEqual(stale_rule_count, 1)

    # -------------------------------------------------------------
    # 5. Deactivation & Audit History Protection
    # -------------------------------------------------------------

    def test_deactivation_stops_schedules_and_cancels_pending_only(self):
        """Deactivating disables rules, cancels pending instances, and preserves completed history."""
        plan = self._create_sample_plan(plan_name="Test Plan Deactivation")
        plan.activate_plan()

        linked_task = frappe.db.get_value("Support Task", {
            "source_doctype": "Custom Care Plan",
            "source_docname": plan.name
        }, "name")

        # Mock a historical completed execution instance
        completed_inst = frappe.new_doc("Support Task Execution Instance")
        completed_inst.support_task = linked_task
        completed_inst.scheduled_date = add_days(today(), -1)
        completed_inst.status = "Delivered"
        completed_inst.executed_by = "Administrator"
        completed_inst.actual_execution_time = now_datetime()
        completed_inst.insert(ignore_permissions=True)

        # Mock a future pending execution instance
        pending_inst = frappe.new_doc("Support Task Execution Instance")
        pending_inst.support_task = linked_task
        pending_inst.scheduled_date = add_days(today(), 2)
        pending_inst.status = "Pending"
        pending_inst.insert(ignore_permissions=True)

        # Deactivate
        plan.deactivate_plan(reason="Client requested plan termination.")

        self.assertEqual(plan.status, "Deactivated")
        self.assertEqual(plan.deactivation_reason, "Client requested plan termination.")

        # Verify historical log is strictly preserved
        completed_inst.reload()
        self.assertEqual(completed_inst.status, "Delivered")

        # Verify pending future instance was cancelled
        pending_inst.reload()
        self.assertEqual(pending_inst.status, "Cancelled")

    def test_prevent_deletion_with_historical_executions(self):
        """Plans with historical execution logs cannot be deleted."""
        plan = self._create_sample_plan(plan_name="Test Plan Protected Trash")
        plan.activate_plan()

        linked_task = frappe.db.get_value("Support Task", {
            "source_doctype": "Custom Care Plan",
            "source_docname": plan.name
        }, "name")

        execution = frappe.new_doc("Support Task Execution Instance")
        execution.support_task = linked_task
        execution.scheduled_date = today()
        execution.status = "Delivered"
        execution.executed_by = "Administrator"
        execution.actual_execution_time = now_datetime()
        execution.insert(ignore_permissions=True)

        self.assertRaises(frappe.ValidationError, plan.delete)
