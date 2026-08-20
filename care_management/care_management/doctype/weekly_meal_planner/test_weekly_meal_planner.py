# Copyright (c) 2026, Hex Flow and Contributors
# See license.txt

from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import ensure_test_participant

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class TestWeeklyMealPlanner(IntegrationTestCase):
	"""
	Integration tests for:

	Weekly Meal Planner
		↓
	Support Task
		↓
	Support Task Schedule Rule
	"""

	def setUp(self):
		super().setUp()

		self.participant = self._get_or_create_test_participant()

		# Remove only test-generated meal planner tasks from previous
		# test executions so each test starts cleanly.
		frappe.db.delete(
			"Support Task",
			{
				"source_doctype": "Weekly Meal Planner",
				"auto_generated": 1,
			},
		)

		frappe.db.delete(
			"Weekly Meal Planner",
			{
				"participant_name": self.participant,
			},
		)

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _get_or_create_test_participant(self):
		return ensure_test_participant()

	def _get_tasks(self, planner_name):
		return frappe.get_all(
			"Support Task",
			filters={
				"source_doctype": "Weekly Meal Planner",
				"source_docname": planner_name,
			},
			fields=[
				"name",
				"task_name",
				"description",
				"status",
				"source_doctype",
				"source_docname",
				"source_row_id",
				"auto_generated",
			],
			order_by="creation asc",
		)

	def _get_task_schedule(self, task_name):
		return frappe.get_all(
			"Support Task Schedule Rule",
			filters={
				"parent": task_name,
				"parenttype": "Support Task",
			},
			fields=[
				"scheduled_time",
				"recurrence_type",
				"start_date",
				"end_date",
				"monday",
				"tuesday",
				"wednesday",
				"thursday",
				"friday",
				"saturday",
				"sunday",
			],
			order_by="idx asc",
		)

	def _create_planner(self):
		planner = frappe.get_doc({
			"doctype": "Weekly Meal Planner",
			"participant_name": self.participant,
			"start_date": "2026-08-10",
			"end_date": "2026-08-16",
			"meal_items": [],
		})

		planner.append("meal_items", {
			"day": "Monday",
			"breakfast": "Oats",
		})

		planner.insert(ignore_permissions=True)

		return planner

	def test_create_one_meal_creates_one_support_task(self):
		planner = self._create_planner()

		tasks = self._get_tasks(planner.name)

		self.assertEqual(len(tasks), 1)

		task = tasks[0]

		self.assertEqual(task.source_doctype, "Weekly Meal Planner")
		self.assertEqual(task.source_docname, planner.name)
		self.assertTrue(task.source_row_id.endswith(":breakfast"))
		self.assertEqual(task.task_name, "Breakfast")
		self.assertEqual(task.description, "Oats")
		self.assertEqual(task.auto_generated, 1)
		self.assertEqual(task.status, "Active")

	def test_meal_task_schedule_uses_planner_date_range(self):
		planner = self._create_planner()

		tasks = self._get_tasks(planner.name)

		self.assertEqual(len(tasks), 1)

		schedules = self._get_task_schedule(tasks[0].name)

		self.assertEqual(len(schedules), 1)

		rule = schedules[0]

		self.assertEqual(str(rule.start_date), "2026-08-10")
		self.assertEqual(str(rule.end_date), "2026-08-16")

		self.assertEqual(rule.scheduled_time, timedelta(hours=7))
		self.assertEqual(rule.recurrence_type, "Selected Days")

		self.assertEqual(rule.monday, 1)

		self.assertEqual(rule.tuesday, 0)
		self.assertEqual(rule.wednesday, 0)
		self.assertEqual(rule.thursday, 0)
		self.assertEqual(rule.friday, 0)
		self.assertEqual(rule.saturday, 0)
		self.assertEqual(rule.sunday, 0)

	def test_second_meal_creates_only_one_additional_task(self):
		planner = self._create_planner()

		self.assertEqual(len(self._get_tasks(planner.name)), 1)

		planner.append("meal_items", {
			"day": "Monday",
			"lunch": "Chicken and rice",
		})

		planner.save(ignore_permissions=True)

		tasks = self._get_tasks(planner.name)

		self.assertEqual(len(tasks), 2)

		source_rows = {
			task.source_row_id
			for task in tasks
		}

		self.assertEqual(len(source_rows), 2)

	def test_existing_meal_task_is_updated_not_duplicated(self):
		planner = self._create_planner()

		tasks_before = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_before), 1)

		task_name_before = tasks_before[0].name

		planner.meal_items[0].breakfast = "Porridge"

		planner.save(ignore_permissions=True)

		tasks_after = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_after), 1)
		self.assertEqual(tasks_after[0].name, task_name_before)
		self.assertEqual(tasks_after[0].description, "Porridge")

	def test_removed_meal_task_is_archived_not_deleted(self):
		planner = self._create_planner()

		tasks_before = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_before), 1)

		task_name = tasks_before[0].name

		planner.meal_items[0].breakfast = ""

		planner.save(ignore_permissions=True)

		tasks_after = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_after), 1)
		self.assertEqual(tasks_after[0].name, task_name)
		self.assertEqual(tasks_after[0].status, "Archived")

	def test_resaving_same_planner_does_not_duplicate_tasks(self):
		planner = self._create_planner()

		tasks_before = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_before), 1)

		planner.save(ignore_permissions=True)
		planner.save(ignore_permissions=True)

		tasks_after = self._get_tasks(planner.name)

		self.assertEqual(len(tasks_after), 1)
		self.assertEqual(tasks_after[0].name, tasks_before[0].name)
