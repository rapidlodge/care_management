import frappe
from frappe.utils import getdate, nowdate, get_first_day_of_week, add_days

from care_management.care_management.utils.task_sync import (
    TRACKER_CONFIG,
    _get_or_create_active_plan,
)


# ============================================================================
# SHIFT CONFIGURATION
# ============================================================================

# Three-shift roster used across the Scheduler.
#
# AM Shift    = 06:00 - 13:59
# PM Shift    = 14:00 - 21:59
# Night Shift = 22:00 - 05:59
#
# Night Shift wraps past midnight.
SHIFT_BOUNDARIES = {
    "AM Shift": (6 * 60, 14 * 60 - 1),
    "PM Shift": (14 * 60, 22 * 60 - 1),
    "Night Shift": (22 * 60, 24 * 60 - 1),
}


# ============================================================================
# TIME / SHIFT HELPERS
# ============================================================================

def _time_to_minutes(time_value):
    """
    Convert HH:MM[:SS] into minutes since midnight.
    """
    parts = str(time_value).split(":")

    return (
        int(parts[0]) * 60
        + int(parts[1])
    )


def _shift_for_time(time_value):
    """
    Determine the roster shift for a given time.

    Night Shift covers:
        22:00 - 23:59
        00:00 - 05:59
    """

    mins = _time_to_minutes(time_value)

    if (
        SHIFT_BOUNDARIES["AM Shift"][0]
        <= mins
        <= SHIFT_BOUNDARIES["AM Shift"][1]
    ):
        return "AM Shift"

    if (
        SHIFT_BOUNDARIES["PM Shift"][0]
        <= mins
        <= SHIFT_BOUNDARIES["PM Shift"][1]
    ):
        return "PM Shift"

    return "Night Shift"


# ============================================================================
# RECURRENCE LOGIC
# ============================================================================

def _rule_occurs_on(rule, check_date):
    """
    Determine whether a Support Task Schedule Rule occurs on check_date.
    """

    start = (
        getdate(rule.get("start_date"))
        if rule.get("start_date")
        else None
    )

    end = (
        getdate(rule.get("end_date"))
        if rule.get("end_date")
        else None
    )

    if start and check_date < start:
        return False

    if end and check_date > end:
        return False

    rtype = rule.get("recurrence_type")

    weekday = check_date.strftime("%A").lower()

    if rtype == "Daily":
        return True

    if rtype == "Selected Days":
        return bool(rule.get(weekday))

    if rtype == "Weekly":
        if not start:
            return bool(rule.get(weekday))

        return (
            check_date - start
        ).days % 7 == 0

    if rtype == "Fortnightly":
        if not start:
            return False

        return (
            check_date - start
        ).days % 14 == 0

    if rtype == "Monthly":
        if not start:
            return False

        return check_date.day == start.day

    if rtype == "Floating / Flexible":
        return True

    return False


# ============================================================================
# WEEK SCHEDULER
# ============================================================================

@frappe.whitelist()
def get_week_tasks(
    start_date,
    participant=None,
    category=None,
    shift=None,
):
    """
    Expand every Active Support Task's recurrence rule into actual
    occurrences that fall inside the requested 7-day window.
    """

    start_date = getdate(start_date)

    week_dates = [
        add_days(start_date, i)
        for i in range(7)
    ]

    conditions = [
        "st.status = 'Active'"
    ]

    params = {}

    # ------------------------------------------------------------
    # PARTICIPANT FILTER
    # ------------------------------------------------------------

    if participant:

        conditions.append(
            "sp.participant = %(participant)s"
        )

        params["participant"] = participant

    # ------------------------------------------------------------
    # CATEGORY FILTER
    # ------------------------------------------------------------

    if category:

        conditions.append(
            "st.task_category = %(category)s"
        )

        params["category"] = category

    where_clause = " AND ".join(
        conditions
    )

    rules = frappe.db.sql(
        f"""
        SELECT
            st.name,
            st.task_name,
            sp.participant,
            st.task_category,
            st.clinical_priority,
            st.description,
            st.staff_count_required,
            st.source_doctype,
            st.source_docname,
            r.scheduled_time,
            r.recurrence_type,
            r.start_date,
            r.end_date,
            r.monday,
            r.tuesday,
            r.wednesday,
            r.thursday,
            r.friday,
            r.saturday,
            r.sunday,
            r.is_floating
        FROM `tabSupport Task` st
        INNER JOIN `tabSupport Plan` sp
            ON st.support_plan = sp.name
        LEFT JOIN `tabSupport Task Schedule Rule` r
            ON r.parent = st.name
            AND r.parenttype = 'Support Task'
        WHERE {where_clause}
        """,
        params,
        as_dict=True,
    )

    occurrences = []

    for rule in rules:

        if not rule.get("scheduled_time"):
            continue

        task_shift = _shift_for_time(
            rule["scheduled_time"]
        )

        # --------------------------------------------------------
        # SHIFT FILTER
        # --------------------------------------------------------

        if shift and task_shift != shift:
            continue

        is_floating = (
            bool(rule.get("is_floating"))
            or
            rule.get("recurrence_type")
            == "Floating / Flexible"
        )

        # --------------------------------------------------------
        # FLOATING TASK
        # --------------------------------------------------------

        if is_floating:

            occ = dict(rule)

            occ["occurrence_date"] = None
            occ["weekday_index"] = None
            occ["shift"] = task_shift
            occ["is_floating"] = 1

            occurrences.append(occ)

            continue

        # --------------------------------------------------------
        # DATED TASK
        # --------------------------------------------------------

        for idx, check_date in enumerate(
            week_dates
        ):

            if _rule_occurs_on(
                rule,
                check_date
            ):

                occ = dict(rule)

                occ["occurrence_date"] = str(
                    check_date
                )

                occ["weekday_index"] = idx

                occ["shift"] = task_shift

                occ["is_floating"] = 0

                occurrences.append(
                    occ
                )

    return occurrences


# ============================================================================
# RECORD TASK DELIVERY
# ============================================================================

@frappe.whitelist()
def _get_task_schedule_context(task_id, scheduled_date=None):
	"""Return the schedule information needed to create an execution instance."""

	scheduled_date = scheduled_date or frappe.utils.nowdate()

	rules = frappe.get_all(
		"Support Task Schedule Rule",
		filters={
			"parent": task_id,
			"parenttype": "Support Task",
		},
		fields=[
			"name",
			"scheduled_time",
			"is_floating",
			"start_date",
			"end_date",
		],
		order_by="idx asc",
		limit=1,
	)

	if not rules:
		frappe.throw(
			f"No active schedule rule was found for Support Task {task_id}."
		)

	rule = rules[0]

	return {
		"scheduled_date": scheduled_date,
		"scheduled_time": rule.scheduled_time,
		"is_floating": int(rule.is_floating or 0),
	}


def _get_existing_execution(
	task_id,
	scheduled_date,
	scheduled_time=None,
):
	"""Return the existing execution instance for this task occurrence."""

	filters = {
		"support_task": task_id,
		"scheduled_date": scheduled_date,
		"docstatus": ["<", 2],
	}

	if scheduled_time:
		filters["scheduled_time"] = scheduled_time

	instances = frappe.get_all(
		"Support Task Execution Instance",
		filters=filters,
		fields=[
			"name",
			"status",
			"outcome",
			"executed_by",
			"actual_execution_time",
		],
		order_by="creation desc",
		limit=1,
	)

	return instances[0] if instances else None


def _get_or_create_execution_instance(
	task_id,
	scheduled_date=None,
	start=False,
):
	"""Get the execution instance for an occurrence or create it."""

	context = _get_task_schedule_context(
		task_id,
		scheduled_date,
	)

	existing = _get_existing_execution(
		task_id,
		context["scheduled_date"],
		context["scheduled_time"],
	)

	if existing:
		return frappe.get_doc(
			"Support Task Execution Instance",
			existing.name,
		)

	instance = frappe.get_doc({
		"doctype": "Support Task Execution Instance",
		"support_task": task_id,
		"scheduled_date": context["scheduled_date"],
		"scheduled_time": context["scheduled_time"],
		"is_floating": context["is_floating"],
		"status": "In Progress" if start else "Pending",
	})

	if start:
		instance.executed_by = frappe.session.user
		instance.actual_execution_time = frappe.utils.now_datetime()

	instance.insert(ignore_permissions=True)

	return instance


@frappe.whitelist()
def start_task_execution(task_id, scheduled_date=None):
	"""Start a scheduled support task."""

	instance = _get_or_create_execution_instance(
		task_id,
		scheduled_date,
		start=True,
	)

	if instance.status in {
		"Delivered",
		"Partially Completed",
		"Refused / Declined",
		"Not Applicable",
		"Missed",
		"Cancelled",
	}:
		return {
			"status": "already_completed",
			"instance": instance.name,
			"execution_status": instance.status,
			"outcome": instance.outcome,
		}

	if instance.status == "Pending":
		instance.status = "In Progress"
		instance.executed_by = frappe.session.user
		instance.actual_execution_time = (
			frappe.utils.now_datetime()
		)
		instance.save(ignore_permissions=True)

	return {
		"status": "success",
		"instance": instance.name,
		"execution_status": instance.status,
		"executed_by": instance.executed_by,
		"actual_execution_time": instance.actual_execution_time,
	}
# ============================================================================
# 	REVIEW TASK EXECUTIONS
# ============================================================================
@frappe.whitelist()
def get_manager_review_tasks(
	start_date=None,
	end_date=None,
	status=None,
	participant=None,
	staff=None,
	follow_up_required=None,
):
	"""
	Return execution instances requiring manager review.

	This is a read-only review endpoint.
	No execution records are modified here.
	"""

	start_date = start_date or frappe.utils.today()
	end_date = end_date or start_date

	filters = {
		"scheduled_date": ["between", [start_date, end_date]],
	}

	if status:
		filters["status"] = status

	if follow_up_required in ("0", "1", 0, 1):
		filters["follow_up_required"] = int(follow_up_required)

	executions = frappe.get_all(
		"Support Task Execution Instance",
		filters=filters,
		fields=[
			"name",
			"support_task",
			"scheduled_date",
			"scheduled_time",
			"status",
			"executed_by",
			"actual_execution_time",
			"outcome",
			"exception_type",
			"follow_up_required",
			"execution_notes",
			"creation",
			"modified",
		],
		order_by="scheduled_date desc, scheduled_time desc",
	)

	results = []

	for execution in executions:

		task = frappe.db.get_value(
			"Support Task",
			execution.support_task,
			[
				"participant",
				"task_name",
			],
			as_dict=True,
		)

		if participant and (
			not task
			or task.participant != participant
		):
			continue

		if staff and execution.executed_by != staff:
			continue

		review_category = "In Progress"
		review_priority = "Low"

		if execution.status == "Missed":
			review_category = "Missed"
			review_priority = "High"

		elif execution.status in {
			"Partially Completed",
			"Refused / Declined",
			"Not Applicable",
		}:
			review_category = "Exception"
			review_priority = "Medium"

		elif execution.exception_type in {
			"Safety Concern",
			"Clinical Concern",
		}:
			review_category = "Exception"
			review_priority = "High"

		elif execution.follow_up_required:
			review_category = "Follow-up"
			review_priority = "Medium"

		elif execution.status == "Delivered":
			review_category = "Completed"
			review_priority = "Low"

		elif execution.status == "Cancelled":
			review_category = "Cancelled"
			review_priority = "Low"

		elif execution.exception_type in {
			"Safety Concern",
			"Clinical Concern",
		}:
			review_category = "Exception"
			review_priority = "High"

		elif execution.status in {
			"Partially Completed",
			"Refused / Declined",
			"Not Applicable",
		}:
			review_category = "Exception"
			review_priority = "Medium"

		elif execution.follow_up_required:
			review_category = "Follow-up"
			review_priority = "Medium"

		results.append({
			"execution_instance": execution.name,
			"support_task": execution.support_task,
			"participant": task.participant if task else None,
			"task_name": task.task_name if task else None,
			"scheduled_date": execution.scheduled_date,
			"scheduled_time": execution.scheduled_time,
			"status": execution.status,
			"outcome": execution.outcome,
			"executed_by": execution.executed_by,
			"actual_execution_time": execution.actual_execution_time,
			"exception_type": execution.exception_type,
			"follow_up_required": execution.follow_up_required,
			"execution_notes": execution.execution_notes,
			"review_category": review_category,
			"review_priority": review_priority,
		})

	return results

@frappe.whitelist()
def record_task_outcome(
	task_id,
	outcome,
	execution_notes=None,
	exception_type=None,
	follow_up_required=0,
	scheduled_date=None,
):
	"""Record the final staff execution outcome."""

	allowed_outcomes = {
		"Completed",
		"Partially Completed",
		"Refused / Declined",
		"Not Applicable",
		"Missed",
		"Cancelled",
	}

	if outcome not in allowed_outcomes:
		frappe.throw(
			f"Invalid execution outcome: {outcome}"
		)

	instance = _get_or_create_execution_instance(
		task_id,
		scheduled_date,
		start=True,
	)

	if instance.status in {
		"Delivered",
		"Partially Completed",
		"Refused / Declined",
		"Not Applicable",
		"Missed",
		"Cancelled",
	}:
		frappe.throw(
			"This task occurrence has already reached a final execution status."
		)

	status_map = {
		"Completed": "Delivered",
		"Partially Completed": "Partially Completed",
		"Refused / Declined": "Refused / Declined",
		"Not Applicable": "Not Applicable",
		"Missed": "Missed",
		"Cancelled": "Cancelled",
	}

	instance.status = status_map[outcome]
	instance.outcome = outcome
	instance.executed_by = instance.executed_by or frappe.session.user
	instance.actual_execution_time = (
		instance.actual_execution_time
		or frappe.utils.now_datetime()
	)
	instance.execution_notes = execution_notes
	instance.exception_type = exception_type
	instance.follow_up_required = int(follow_up_required or 0)

	instance.save(ignore_permissions=True)

	# ------------------------------------------------------------
	# IMMUTABLE AUDIT RECORDS
	# ------------------------------------------------------------

	log_name = None
	
	if outcome == "Completed":
		existing_log = frappe.db.exists(
			"Support Task Delivery Log",
			{
				"execution_instance": instance.name
			},
		)

		if existing_log:
			frappe.throw(
				"This execution already has a delivery audit record."
			)
		log = frappe.get_doc({
			"doctype": "Support Task Delivery Log",
			"execution_instance": instance.name,
			"primary_staff": instance.executed_by,
			"delivered_timestamp": instance.actual_execution_time,
			"delivery_notes": execution_notes or "",
		})

		log.insert(ignore_permissions=True)
		log_name = log.name

	elif outcome == "Missed":
		existing_log = frappe.db.exists(
			"Support Task Missed Log",
			{
				"execution_instance": instance.name
			},
		)

		if existing_log:
			frappe.throw(
				"This execution already has a missed-task audit record."
			)
		log = frappe.get_doc({
			"doctype": "Support Task Missed Log",
			"execution_instance": instance.name,
			"logged_by_staff": instance.executed_by,
			"missed_timestamp": instance.actual_execution_time,
			"reason_category": exception_type or "Other",
			"incident_escalated": 0,
			"omission_notes": execution_notes or "",
		})

		log.insert(ignore_permissions=True)
		log_name = log.name

	frappe.db.commit()

	return {
		"status": "success",
		"instance": instance.name,
		"execution_status": instance.status,
		"outcome": instance.outcome,
		"log": log_name,
	}
# ============================================================================
# TRACKER HELPERS
# ============================================================================

def _tracker_for_category(
    task_category,
):
    """
    Find the tracker DocType associated with a Support Task category.
    """

    for tracker_doctype, config in TRACKER_CONFIG.items():

        if (
            task_category
            in config.get(
                "task_categories",
                [],
            )
        ):

            return tracker_doctype

    return None


# ============================================================================
# AUTOMATIC TRACKER ENTRY
# ============================================================================

def _auto_append_tracker_entry(tracker_doctype, participant, delivery_notes):
	"""
	Create an automatic tracker entry when a Support Task is delivered.

	Important:
	- Build the child row first.
	- Populate automatic mandatory fields.
	- If the parent does not exist, append the child row BEFORE insert().
	"""

	config = TRACKER_CONFIG[tracker_doctype]

	ref_date = getdate(nowdate())

	# ---------------------------------------------------------
	# Build the child row FIRST
	# ---------------------------------------------------------

	row = _default_row(
		config["item_doctype"],
		ref_date
	)

	# Add delivery notes when the child DocType supports it
	if delivery_notes:
		for notes_field in ("comments", "notes"):
			if (
				notes_field in config.get("matrix_fields", [])
				or _doctype_has_field(
					config["item_doctype"],
					notes_field
				)
			):
				row[notes_field] = delivery_notes
				break

	# ---------------------------------------------------------
	# Find existing parent or create new parent WITH row
	# ---------------------------------------------------------

	parent_name, created = _find_or_create_tracker_parent(
		tracker_doctype,
		participant,
		config,
		ref_date,
		initial_row=row
	)

	# ---------------------------------------------------------
	# Existing parent
	# ---------------------------------------------------------

	if not created:

		parent_doc = frappe.get_doc(
			tracker_doctype,
			parent_name
		)

		parent_doc.append(
			config["child_table"],
			row
		)

		parent_doc.save(
			ignore_permissions=True
		)

	# ---------------------------------------------------------
	# Mirror into Support Plan
	# ---------------------------------------------------------

	_mirror_to_support_plan(
		tracker_doctype,
		participant,
		[row]
	)
# ============================================================================
# SAVE TRACKER MATRIX
# ============================================================================

@frappe.whitelist()
def save_tracker_matrix_entries(
	participant,
	tracker_doctype,
	rows
):
	"""
	Save tracker matrix rows.

	Automatically derives fields such as:
	- month
	- day_of_month
	- day
	- day_of_week
	- date
	- time

	where those fields exist in the child DocType.

	User-entered clinical/qualitative mandatory fields remain
	required and must be supplied from the grid.
	"""

	import json as _json

	# ---------------------------------------------------------
	# Normalize JSON input
	# ---------------------------------------------------------

	if isinstance(rows, str):
		rows = _json.loads(rows)

	if not isinstance(rows, list):
		frappe.throw(
			"Tracker rows must be a list."
		)

	# ---------------------------------------------------------
	# Validate tracker
	# ---------------------------------------------------------

	if tracker_doctype not in TRACKER_CONFIG:
		frappe.throw(
			f"{tracker_doctype} is not a registered tracker DocType."
		)

	config = TRACKER_CONFIG[tracker_doctype]

	touched_parents = {}
	saved = 0

	child_fields = _child_fieldnames(
		config["item_doctype"]
	)

	# ---------------------------------------------------------
	# Process each matrix row
	# ---------------------------------------------------------

	for incoming_row in rows:

		if not isinstance(incoming_row, dict):
			continue

		# -----------------------------------------------------
		# Determine date
		# -----------------------------------------------------

		if incoming_row.get("date"):
			row_date = getdate(
				incoming_row["date"]
			)
		else:
			row_date = getdate(
				nowdate()
			)

		# -----------------------------------------------------
		# START WITH AUTOMATIC DEFAULTS
		#
		# This is the important fix.
		#
		# Previously clean_row started empty and therefore
		# day_of_month/month were missing.
		# -----------------------------------------------------

		clean_row = _default_row(
			config["item_doctype"],
			row_date
		)

		# -----------------------------------------------------
		# Copy user-entered values over the defaults
		# -----------------------------------------------------

		for fieldname in config.get(
			"matrix_fields",
			[]
		):

			value = incoming_row.get(
				fieldname
			)

			if value not in (
				None,
				""
			):

				clean_row[fieldname] = value

		# -----------------------------------------------------
		# Ensure date is always correct
		# -----------------------------------------------------

		if "date" in child_fields:
			clean_row["date"] = row_date

		# -----------------------------------------------------
		# Automatically derive month
		# -----------------------------------------------------

		if "month" in child_fields:

			# Mood Tracker uses full month names:
			# January, February, March, etc.
			clean_row["month"] = (
				row_date.strftime("%B")
			)

		# -----------------------------------------------------
		# Automatically derive day_of_month
		# -----------------------------------------------------

		if "day_of_month" in child_fields:

			clean_row["day_of_month"] = (
				row_date.day
			)

		# -----------------------------------------------------
		# Automatically derive day
		# -----------------------------------------------------

		if "day" in child_fields:

			clean_row["day"] = (
				row_date.strftime("%A")
			)

		# -----------------------------------------------------
		# Automatically derive day_of_week
		# -----------------------------------------------------

		if "day_of_week" in child_fields:

			clean_row["day_of_week"] = (
				row_date.strftime("%A")
			)

		# -----------------------------------------------------
		# Automatically derive time if the field exists
		# -----------------------------------------------------

		if (
			"time" in child_fields
			and not clean_row.get("time")
		):

			clean_row["time"] = (
				frappe.utils.nowtime()
			)

		# -----------------------------------------------------
		# Automatically populate staff identity
		# -----------------------------------------------------

		if "staff_initials" in child_fields:

			clean_row.setdefault(
				"staff_initials",
				frappe.session.user
			)

		if "staff_signature" in child_fields:

			clean_row.setdefault(
				"staff_signature",
				frappe.session.user
			)

		if "initial" in child_fields:

			clean_row.setdefault(
				"initial",
				frappe.session.user
			)
		# IMPORTANT:
		# The fully prepared child row is passed to the helper.
		# -----------------------------------------------------

		parent_name, created = (
			_find_or_create_tracker_parent(
				tracker_doctype,
				participant,
				config,
				row_date,
				initial_row=clean_row
			)
		)

		# -----------------------------------------------------
		# Load parent only once
		# -----------------------------------------------------

		if parent_name not in touched_parents:

			touched_parents[parent_name] = (
				frappe.get_doc(
					tracker_doctype,
					parent_name
				)
			)

		parent_doc = (
			touched_parents[parent_name]
		)

		# -----------------------------------------------------
		# If parent was newly created, initial_row was already
		# inserted into it.
		#
		# Therefore DO NOT append it again.
		# -----------------------------------------------------

		if not created:

			parent_doc.append(
				config["child_table"],
				clean_row
			)

		saved += 1

	# ---------------------------------------------------------
	# Save all touched parents
	# ---------------------------------------------------------

	for parent_doc in touched_parents.values():

		parent_doc.save(
			ignore_permissions=True
		)

	# ---------------------------------------------------------
	# Mirror into Support Plan
	# ---------------------------------------------------------

	_mirror_to_support_plan(
		tracker_doctype,
		participant,
		rows
	)

	frappe.db.commit()

	return {
		"status": "success",
		"rows_saved": saved,
		"documents_updated": list(
			touched_parents.keys()
		)
	}# ============================================================================
# MIRROR TRACKER ROWS TO SUPPORT PLAN
# ============================================================================

def _mirror_to_support_plan(
    tracker_doctype,
    participant,
    rows
):
    """
    Mirror tracker matrix rows into the participant's Support Plan.

    The Support Plan child row may have mandatory derived fields such as:
        - date
        - month
        - day_of_month
        - day
        - day_of_week

    Those fields are generated server-side from the row date.

    Tracker-specific fields are copied only when the corresponding
    field exists on the Support Plan child DocType.
    """

    config = TRACKER_CONFIG.get(
        tracker_doctype
    )

    if not config:
        return

    plan_field = config.get(
        "support_plan_child_table"
    )

    if not plan_field:
        return

    # ---------------------------------------------------------
    # Get active Support Plan
    # ---------------------------------------------------------

    plan_name = _get_or_create_active_plan(
        participant
    )

    if not plan_name:
        return

    plan_doc = frappe.get_doc(
        "Support Plan",
        plan_name
    )

    # ---------------------------------------------------------
    # Validate Support Plan field
    # ---------------------------------------------------------

    plan_meta = frappe.get_meta(
        "Support Plan"
    )

    plan_field_meta = plan_meta.get_field(
        plan_field
    )

    if not plan_field_meta:
        frappe.log_error(
            title="Invalid Support Plan Mirror Field",
            message=(
                f"Tracker: {tracker_doctype}\n"
                f"Participant: {participant}\n"
                f"Support Plan: {plan_name}\n"
                f"Field: {plan_field}"
            )
        )
        return

    if plan_field_meta.fieldtype != "Table":
        frappe.log_error(
            title="Support Plan Mirror Field Is Not Table",
            message=(
                f"Tracker: {tracker_doctype}\n"
                f"Field: {plan_field}\n"
                f"Field Type: {plan_field_meta.fieldtype}"
            )
        )
        return

    # ---------------------------------------------------------
    # Get Support Plan child DocType
    # ---------------------------------------------------------

    support_plan_child_doctype = (
        plan_field_meta.options
    )

    if not support_plan_child_doctype:
        return

    support_child_meta = frappe.get_meta(
        support_plan_child_doctype
    )

    support_child_fields = {
        df.fieldname
        for df in support_child_meta.fields
    }

    # ---------------------------------------------------------
    # Process rows
    # ---------------------------------------------------------

    for incoming_row in rows:

        if not isinstance(
            incoming_row,
            dict
        ):
            continue

        # -----------------------------------------------------
        # Determine row date
        # -----------------------------------------------------

        row_date = incoming_row.get(
            "date"
        )

        if row_date:
            row_date = getdate(
                row_date
            )
        else:
            row_date = getdate(
                nowdate()
            )

        # -----------------------------------------------------
        # Start with derived defaults FOR THE SUPPORT PLAN
        #
        # This is the important difference from the previous
        # implementation.
        # -----------------------------------------------------

        clean_row = {}

        if "date" in support_child_fields:
            clean_row["date"] = row_date

        if "month" in support_child_fields:
            clean_row["month"] = (
                row_date.strftime("%B")
            )

        if "day_of_month" in support_child_fields:
            clean_row["day_of_month"] = (
                row_date.day
            )

        if "day" in support_child_fields:
            clean_row["day"] = (
                row_date.strftime("%A")
            )

        if "day_of_week" in support_child_fields:
            clean_row["day_of_week"] = (
                row_date.strftime("%A")
            )

        # -----------------------------------------------------
        # Copy tracker values ONLY if the Support Plan child
        # actually has the same field.
        # -----------------------------------------------------

        for fieldname, value in incoming_row.items():

            if fieldname not in support_child_fields:
                continue

            if value in (
                None,
                ""
            ):
                continue

            clean_row[fieldname] = value

        # -----------------------------------------------------
        # Append to Support Plan
        # -----------------------------------------------------

        if clean_row:

            plan_doc.append(
                plan_field,
                clean_row
            )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    if plan_doc.get(plan_field):

        plan_doc.save(
            ignore_permissions=True
        )

# ============================================================================
# FIND / CREATE TRACKER PARENT
# ============================================================================

def _find_or_create_tracker_parent(
	tracker_doctype,
	participant,
	config,
	ref_date,
	initial_row=None
):
	"""
	Find an existing tracker parent or create a new one.

	If a new parent is required and its child table is mandatory,
	initial_row is appended BEFORE insert().
	"""

	group_by = config["group_by"]

	filters = {
		config["participant_field"]:
			participant
	}

	new_doc = {
		"doctype":
			tracker_doctype,

		config["participant_field"]:
			participant
	}

	# ---------------------------------------------------------
	# SINGLE
	# ---------------------------------------------------------

	if group_by == "single":

		pass

	# ---------------------------------------------------------
	# WEEK
	# ---------------------------------------------------------

	elif group_by == "week":

		week_start = get_first_day_of_week(
			ref_date
		)

		field = config["week_field"]

		filters[field] = week_start
		new_doc[field] = week_start

	# ---------------------------------------------------------
	# DAY
	# ---------------------------------------------------------

	elif group_by == "day":

		field = config["day_field"]

		filters[field] = ref_date
		new_doc[field] = ref_date

	# ---------------------------------------------------------
	# YEAR
	# ---------------------------------------------------------

	elif group_by == "year":

		filters["year"] = (
			str(ref_date.year)
		)

		new_doc["year"] = (
			str(ref_date.year)
		)

	# ---------------------------------------------------------
	# MONTH / YEAR
	# ---------------------------------------------------------

	elif group_by == "month_year":

		month_abbr = (
			ref_date
			.strftime("%b")
			.upper()
		)

		filters["month"] = month_abbr
		filters["year"] = (
			str(ref_date.year)
		)

		new_doc["month"] = month_abbr
		new_doc["year"] = (
			str(ref_date.year)
		)

	# ---------------------------------------------------------
	# Look for existing parent
	# ---------------------------------------------------------

	existing = frappe.db.get_value(
		tracker_doctype,
		filters,
		"name"
	)

	if existing:

		return (
			existing,
			False
		)

	# ---------------------------------------------------------
	# Create parent
	# ---------------------------------------------------------

	doc = frappe.get_doc(
		new_doc
	)

	# ---------------------------------------------------------
	# CRITICAL:
	# Add first child BEFORE insert().
	# ---------------------------------------------------------

	if initial_row:

		child_table = config[
			"child_table"
		]

		doc.append(
			child_table,
			initial_row
		)

	# ---------------------------------------------------------
	# Now insert parent
	# ---------------------------------------------------------

	doc.insert(
		ignore_permissions=True
	)

	return (
		doc.name,
		True
	)# ============================================================================
# DEFAULT CHILD ROW
# ============================================================================

def _default_row(item_doctype, ref_date):
	"""
	Populate fields that can safely be derived from the date/time.

	Clinical fields such as Mood, Stool Type, Pain, etc. are NOT
	automatically guessed.
	"""

	row = {}

	fieldnames = _child_fieldnames(
		item_doctype
	)

	# ---------------------------------------------------------
	# Date
	# ---------------------------------------------------------

	if "date" in fieldnames:
		row["date"] = ref_date

	# ---------------------------------------------------------
	# Time
	# ---------------------------------------------------------

	if "time" in fieldnames:
		row["time"] = frappe.utils.nowtime()

	# ---------------------------------------------------------
	# Day
	# ---------------------------------------------------------

	if "day" in fieldnames:
		row["day"] = ref_date.strftime(
			"%A"
		)

	# ---------------------------------------------------------
	# Day of Week
	# ---------------------------------------------------------

	if "day_of_week" in fieldnames:
		row["day_of_week"] = ref_date.strftime(
			"%A"
		)

	# ---------------------------------------------------------
	# Month
	# ---------------------------------------------------------

	if "month" in fieldnames:
		row["month"] = ref_date.strftime(
			"%B"
		)

	# ---------------------------------------------------------
	# Day of Month
	# ---------------------------------------------------------

	if "day_of_month" in fieldnames:
		row["day_of_month"] = (
			ref_date.day
		)

	return row
# ============================================================================
# DOCTYPE FIELD HELPERS
# ============================================================================

def _child_fieldnames(
    item_doctype,
):
    """
    Return all fieldnames from a Child Table DocType.
    """

    meta = frappe.get_meta(
        item_doctype
    )

    return [
        f.fieldname
        for f in meta.fields
    ]


def _doctype_has_field(
    item_doctype,
    fieldname,
):
    """
    Check whether a DocType contains a field.
    """

    return (
        fieldname
        in _child_fieldnames(
            item_doctype
        )
    )