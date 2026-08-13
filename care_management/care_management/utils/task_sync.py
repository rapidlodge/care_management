"""
Support Task Sync Engine
=========================
Generic engine that reads "source" master documents (Weekly Meal Planner,
Appointment Schedule, Falls Risk Plan, etc.) and auto-generates / keeps in
sync the matching Support Task records that appear on the Active Support
Task Scheduler matrix.

Design
------
Every Support Task created by this engine is tagged with a generic triple:
    source_doctype  -> the DocType it came from (e.g. "Weekly Meal Planner")
    source_docname  -> the specific document (e.g. "MEAL-0001")
    source_row_id   -> the child-table row `name` it was exploded from
                        (empty for "single" documents that don't have rows)

That triple is the "common field" that ties every Support Task back to
whatever produced it, instead of one dedicated Link field per source
DocType. Adding a new source DocType only means adding an entry to
SCHEDULE_SOURCE_CONFIG below - no schema changes on Support Task.

Sync is idempotent: on every `on_update` of a registered source document,
we recompute the *desired* set of tasks from its current rows/state, then
diff against the tasks we previously generated (found via the
source_doctype + source_docname pair):
    - matching row  -> update task_name/time/weekdays if they changed
    - new row       -> create a new Support Task
    - row no longer present -> archive the orphaned Support Task
        (never hard-deleted, so delivery/missed history is preserved)

Explode strategies
-------------------
"single"        : the whole document maps to exactly one Support Task
                   (no source_row_id). Good for plan-type docs that are
                   reviewed/actioned as a whole (Falls Risk Plan, Epilepsy
                   Management Plan, Hospital Support Plan).

"rows"          : each child-table row becomes its own Support Task, using
                   a date field on the row for the one-off schedule.
                   Good for Appointment Schedule.

"weekday_row"   : each child-table row already carries its own
                   Mon..Sun checkboxes (a mini recurrence rule) - one row
                   becomes one recurring Support Task using those same
                   checkboxes. Good for Daily Cleaning Task Checklist /
                   Daily Shift Task Checklist.

"meal_columns"  : each row is one weekday with several meal-time columns
                   (breakfast/lunch/dinner/...). Every *populated* column
                   becomes its own weekly-recurring Support Task at a
                   fixed default time for that column. Good for Weekly
                   Meal Planner.
"""

import frappe
from frappe.utils import nowdate, cstr

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Maps the Select options used on Medication Plan Item / Medication
# Administration Log's time_slot field to an actual clock time.
TIME_SLOT_MAP = {
	"6 AM": "06:00:00",
	"8 AM": "08:00:00",
	"12 PM (Lunch)": "12:00:00",
	"6 PM (Dinner)": "18:00:00",
	"8 PM (Bedtime)": "20:00:00",
}

# ---------------------------------------------------------------------------
# 1. SCHEDULE SOURCE CONFIG
#    DocTypes that auto-generate forward-looking Support Tasks.
# ---------------------------------------------------------------------------
SCHEDULE_SOURCE_CONFIG = {
	"Weekly Meal Planner": {
		"participant_field": "participant_name",
		"explode": "meal_columns",
		"child_table": "meal_items",
		"day_field": "day",
		"task_category": "Meal Preparation",
		"clinical_priority": "Mandatory",
		"columns": {
			"breakfast": ("Breakfast", "07:00:00"),
			"morning_tea": ("Morning Tea", "10:00:00"),
			"lunch": ("Lunch", "12:30:00"),
			"afternoon_tea": ("Afternoon Tea", "15:00:00"),
			"dinner": ("Dinner", "18:00:00"),
			"supper": ("Supper", "20:00:00"),
		},
	},
	"Appointment Schedule": {
		"participant_field": "participant",
		"explode": "rows",
		"child_table": "schedule_items",
		"date_field": "appointment_date",
		"label_field": "medical_appointment",
		"default_time": "09:00:00",
		"task_category": "Community Access",
		"clinical_priority": "Clinical",
	},
	"Daily Cleaning Task Checklist": {
		"participant_field": "participant",
		"explode": "weekday_row",
		"child_table": "cleaning_tasks",
		"label_field": "task_description",
		"default_time": "12:00:00",
		"task_category": "Shift Task",
		"clinical_priority": "Optional",
	},
	"Daily Shift Task Checklist": {
		"participant_field": "participant",
		"explode": "weekday_row",
		"child_table": "shift_tasks",
		"label_field": "task_description",
		"default_time": "08:00:00",
		"task_category": "Shift Task",
		"clinical_priority": "Mandatory",
	},
	"Medication Administration Log": {
		"participant_field": "participant",
		"explode": "weekday_row",
		"child_table": "medication_items",
		"label_field": "medication_name",
		"detail_field": "dosage",
		"time_field": "time_slot",
		"time_map": TIME_SLOT_MAP,
		"prn_field": "is_prn",
		"default_time": "08:00:00",
		"task_category": "Medication",
		"clinical_priority": "Clinical",
	},
	"Falls Risk Plan": {
		"participant_field": "participant_name",
		"explode": "single",
		"default_time": "08:00:00",
		"task_category": "Personal Care",
		"clinical_priority": "Clinical",
		"task_name": "Falls Risk Supervision & Mobility Check",
	},
	"Epilepsy Management Plan": {
		"participant_field": "participant",
		"explode": "single",
		"default_time": "06:00:00",
		"task_category": "Clinical Observation",
		"clinical_priority": "Critical",
		"task_name": "Epilepsy Monitoring & Safety Check",
	},
	"Hospital Support Plan": {
		"participant_field": "participant",
		"explode": "single",
		"default_time": "08:00:00",
		"task_category": "Clinical Observation",
		"clinical_priority": "Clinical",
		"task_name": "Hospital Plan Review",
	},
	# NOTE: Staff Shift Handover Sheet is intentionally excluded - it has no
	# participant field (it's a shift-level document, not participant-level),
	# so it can't map onto a per-participant Support Plan / Support Task.
}

# ---------------------------------------------------------------------------
# 2. TRACKER CONFIG
#    Standalone chart/tracker DocTypes staff fill in via the matrix grid on
#    the Scheduler page, and that Support Task completion can auto-append
#    to. These are NOT auto-scheduled - they are logged as care happens.
# ---------------------------------------------------------------------------
TRACKER_CONFIG = {
	"Mood Tracker": {
		"support_plan_child_table": "mooed_tracker_entry",
		"participant_field": "participant",
		"child_table": "mood_entries",
		"item_doctype": "Mood Tracker Entry",
		"group_by": "year",  # one Mood Tracker doc per participant per year
		"task_categories": [],  # not auto-appended from task delivery (staff-logged directly)
		"matrix_fields": ["date", "mood", "notes"],
	},
	"Sleep Tracker": {
		"support_plan_child_table": "sleep_tracker_entry",
		"participant_field": "participant",
		"child_table": "sleep_entries",
		"item_doctype": "Sleep Tracker Entry",
		"group_by": "month_year",  # one Sleep Tracker doc per participant per month
		"task_categories": [],
		"matrix_fields": ["date", "am_hours_asleep", "pm_hours_asleep", "quality_of_sleep", "notes"],
	},
	"Shower Chart": {
		"support_plan_child_table": "shower_chart_entries",
		"participant_field": "participant",
		"child_table": "shower_chart_items",
		"item_doctype": "Shower Chart Item",
		"group_by": "week",  # one Shower Chart doc per participant per week_starting_date
		"week_field": "week_starting_date",
		"task_categories": ["Personal Care"],
		"matrix_fields": ["day", "shift", "type", "hair_washed", "comments"],
	},
	"Daily Bowel Record Chart": {
		"support_plan_child_table": "daily_bowel_record_entries",
		"participant_field": "participant",
		"child_table": "bowel_record_items",
		"item_doctype": "Daily Bowel Record Item",
		"group_by": "single",  # one ongoing Daily Bowel Record Chart doc per participant
		"task_categories": ["Bowel & Fluid"],
		"matrix_fields": ["date", "time", "stool_type", "pains_or_distress", "where_stool_passed"],
	},
	"Fluid Intake Output Chart": {
		"support_plan_child_table": "fluid_intake_output_entries",
		"participant_field": "participant",
		"child_table": "fluid_intake_items",
		"item_doctype": "Fluid Intake Item",
		"group_by": "day",  # one Fluid Intake Output Chart doc per participant per chart_date
		"day_field": "chart_date",
		"task_categories": ["Bowel & Fluid"],
		"matrix_fields": ["date", "time", "type_of_fluid", "amount_ml"],
	},
	"Weekly Exercise Record": {
		"support_plan_child_table": "weekly_exercise_record",
		"participant_field": "participant",
		"child_table": "exercise_items",
		"item_doctype": "Exercise Record Item",
		"group_by": "week",
		"week_field": "week_start_date",
		"task_categories": ["Exercise & Therapy"],
		"matrix_fields": ["day_of_week", "shift", "date", "time", "duration_minutes", "location", "notes"],
	},
	"Seizure Chart": {
		"support_plan_child_table": "seizure",
		"participant_field": "participant",
		"child_table": "seizure_entries",
		"item_doctype": "Seizure Chart Entry",
		"group_by": "single",
		"task_categories": ["Clinical Observation"],
		"matrix_fields": ["date", "time", "duration", "description"],
	},
}


def sync_doc_to_support_task(doc, method=None):
	"""Entry point wired into hooks.py doc_events on_update for every
	DocType listed in SCHEDULE_SOURCE_CONFIG."""

	config = SCHEDULE_SOURCE_CONFIG.get(doc.doctype)
	if not config:
		return

	participant = getattr(doc, config["participant_field"], None)
	if not participant:
		return

	plan_name = _get_or_create_active_plan(participant)

	desired = _build_desired_tasks(doc, config)
	_reconcile_tasks(doc.doctype, doc.name, plan_name, config, desired)

	frappe.db.commit()


def _get_or_create_active_plan(participant):
	plan_name = frappe.db.get_value(
		"Support Plan", {"participant": participant, "status": "Active"}, "name"
	)
	if plan_name:
		return plan_name

	plan_doc = frappe.get_doc({
		"doctype": "Support Plan",
		"participant": participant,
		"plan_name": f"Master Care Plan for {participant}",
		"status": "Active",
		"start_date": nowdate(),
	})
	plan_doc.insert(ignore_permissions=True)
	return plan_doc.name


def _build_desired_tasks(doc, config):
	"""Return the Support Tasks that should exist for the source document.

	Each returned item contains:
		- row_id
		- task_name
		- description
		- schedule_rule

	The function intentionally uses the existing source configuration and
	explosion strategies. Weekly Meal Planner is the first source for which
	the source document's own date range is applied to the generated
	recurrence rule.
	"""
	explode = config["explode"]

	if explode == "single":
		return [{
			"row_id": "",
			"task_name": config["task_name"],
			"description": f"Auto-generated task from {doc.doctype}: {doc.name}",
			"schedule_rule": {
				"scheduled_time": config["default_time"],
				"recurrence_type": "Daily",
				"start_date": nowdate(),
				**{d: 1 for d in WEEKDAYS},
			},
		}]

	if explode == "meal_columns":
		out = []

		# ------------------------------------------------------------
		# WEEKLY MEAL PLANNER DATE RANGE
		# ------------------------------------------------------------
		#
		# The meal planner is the source of truth for the period during
		# which the recurring meal requirements are active.
		#
		# If start_date is not supplied, retain the existing behaviour
		# of starting from today.
		#
		# If end_date is supplied, pass it to the Support Task schedule
		# rule so the scheduler stops generating occurrences after that
		# date.
		#
		meal_start_date = cstr(doc.get("start_date") or nowdate())
		meal_end_date = doc.get("end_date")

		if meal_end_date:
			meal_end_date = cstr(meal_end_date)

		for row in doc.get(config["child_table"]) or []:
			day = (row.get(config["day_field"]) or "").strip().lower()

			if day not in WEEKDAYS:
				continue

			for fieldname, (label, default_time) in config["columns"].items():
				value = (row.get(fieldname) or "").strip()

				if not value:
					continue

				schedule_rule = {
					"scheduled_time": default_time,
					"recurrence_type": "Selected Days",
					"start_date": meal_start_date,
					**{
						d: (1 if d == day else 0)
						for d in WEEKDAYS
					},
				}

				if meal_end_date:
					schedule_rule["end_date"] = meal_end_date

				out.append({
					"row_id": f"{row.name}:{fieldname}",
					"task_name": label,
					"description": value,
					"schedule_rule": schedule_rule,
				})

		return out

	if explode == "rows":
		out = []

		for row in doc.get(config["child_table"]) or []:
			row_date = row.get(config["date_field"])

			if not row_date:
				continue

			label = (
				row.get(config["label_field"])
				or config.get("task_category", "Task")
			)

			weekday = frappe.utils.get_datetime(
				row_date
			).strftime("%A").lower()

			out.append({
				"row_id": row.name,
				"task_name": label,
				"description": f"Scheduled for {row_date}",
				"schedule_rule": {
					"scheduled_time": config["default_time"],
					"recurrence_type": "Selected Days",
					"start_date": cstr(row_date),
					"end_date": cstr(row_date),
					**{
						d: (1 if d == weekday else 0)
						for d in WEEKDAYS
					},
				},
			})

		return out

	if explode == "weekday_row":
		out = []

		prn_field = config.get("prn_field")
		time_field = config.get("time_field")
		time_map = config.get("time_map", {})
		detail_field = config.get("detail_field")

		for row in doc.get(config["child_table"]) or []:
			label = row.get(config["label_field"])

			if not label:
				continue

			if prn_field and row.get(prn_field):
				continue

			days_on = {
				d: (1 if row.get(d) else 0)
				for d in WEEKDAYS
			}

			if not any(days_on.values()):
				continue

			scheduled_time = config["default_time"]

			if time_field and row.get(time_field):
				scheduled_time = time_map.get(
					row.get(time_field),
					config["default_time"],
				)

			task_name = label

			if detail_field and row.get(detail_field):
				task_name = (
					f"{label} ({row.get(detail_field)})"
				)

			out.append({
				"row_id": row.name,
				"task_name": task_name,
				"description": (
					f"Auto-generated task from "
					f"{doc.doctype}: {doc.name}"
				),
				"schedule_rule": {
					"scheduled_time": scheduled_time,
					"recurrence_type": "Selected Days",
					"start_date": nowdate(),
					**days_on,
				},
			})

		return out

	return []

def _reconcile_tasks(source_doctype, source_docname, plan_name, config, desired):
	existing = frappe.get_all(
		"Support Task",
		filters={"source_doctype": source_doctype, "source_docname": source_docname},
		fields=["name", "source_row_id", "task_name", "status"],
	)
	existing_by_row = {e.source_row_id or "": e for e in existing}
	desired_row_ids = {d["row_id"] for d in desired}

	# create / update
	for spec in desired:
		match = existing_by_row.get(spec["row_id"])
		if match:
			task_doc = frappe.get_doc("Support Task", match.name)
			task_doc.task_name = spec["task_name"]
			task_doc.description = spec["description"]
			if task_doc.status == "Archived":
				task_doc.status = "Active"
			task_doc.set("schedule_rules", [spec["schedule_rule"]])
			task_doc.save(ignore_permissions=True)
		else:
			task_doc = frappe.get_doc({
				"doctype": "Support Task",
				"task_name": spec["task_name"],
				"support_plan": plan_name,
				"task_category": config["task_category"],
				"status": "Active",
				"clinical_priority": config.get("clinical_priority", "Mandatory"),
				"staff_count_required": 1,
				"description": spec["description"],
				"source_doctype": source_doctype,
				"source_docname": source_docname,
				"source_row_id": spec["row_id"],
				"auto_generated": 1,
				"schedule_rules": [spec["schedule_rule"]],
			})
			task_doc.insert(ignore_permissions=True)

	# archive orphans (row removed from source doc since last sync)
	for row_id, e in existing_by_row.items():
		if row_id not in desired_row_ids and e.status != "Archived":
			frappe.db.set_value("Support Task", e.name, "status", "Archived")
