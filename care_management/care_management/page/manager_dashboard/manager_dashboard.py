import frappe


@frappe.whitelist()
def get_manager_dashboard_data(
    start_date=None,
    end_date=None,
    status=None,
    participant=None
):
    """
    Manager Dashboard KPI and review data.

    Phase 3B.1:
    - Calculates KPI values independently.
    - Retrieves Manager Review records separately.
    - Keeps the existing Manager Review business logic as
      the authoritative source for review records.
    """

    if not start_date:
        start_date = frappe.utils.today()

    if not end_date:
        end_date = start_date


    if start_date > end_date:

        frappe.throw(
            "Start Date cannot be after End Date."
        )


    # ------------------------------------------------------------
    # Manager Review records
    # ------------------------------------------------------------

    reviews = get_manager_review_tasks(
        start_date=start_date,
        end_date=end_date,
        status=status,
        participant=participant
    )


    reviews = reviews or []


    # ------------------------------------------------------------
    # KPI calculation
    # ------------------------------------------------------------

    kpis = calculate_kpis(
        reviews
    )
    attention_items = get_manager_attention_items(
        start_date=start_date,
        end_date=end_date,
        participant=participant
    )
    follow_up_items = get_manager_attention_items(
        start_date=start_date,
        end_date=end_date,
        attention_type="follow_up",
        participant=participant
    )

    return {

        "kpis":
            kpis,

        "attention_items":
            attention_items,

        "follow_up_count":
            len(
                follow_up_items
            ),

        "reviews":
            reviews

    }

# ================================================================
# EXECUTION REVIEW DETAIL
# ================================================================

# ================================================================
# EXECUTION REVIEW DETAIL
# ================================================================

@frappe.whitelist()
def get_execution_review_detail(
    execution_instance
):
    """
    Return the complete manager-review information for one
    Support Task Execution Instance.

    Phase 3B.5

    IMPORTANT:
    The execution_instance received from the Manager Dashboard
    is the actual name of the Support Task Execution Instance
    document.

    We therefore retrieve the execution directly instead of
    searching through the derived Manager Review list.
    """

    if not execution_instance:

        frappe.throw(
            "Execution Instance is required."
        )


    execution_instance = str(
        execution_instance
    ).strip()


    # ------------------------------------------------------------
    # Verify the execution exists
    # ------------------------------------------------------------

    if not frappe.db.exists(
        "Support Task Execution Instance",
        execution_instance
    ):

        frappe.throw(
            "Execution record not found."
        )


    # ------------------------------------------------------------
    # Load the actual execution document
    # ------------------------------------------------------------

    execution = frappe.get_doc(
        "Support Task Execution Instance",
        execution_instance
    )


    # ------------------------------------------------------------
    # Safely read fields
    #
    # getattr(..., None) is intentional because this allows the
    # dashboard to remain compatible if optional fields are not
    # present on the execution DocType.
    # ------------------------------------------------------------

    task = frappe.get_doc(
		"Support Task",
		execution.support_task
	)

    participant = frappe.db.get_value(
		"Support Plan",
		task.support_plan,
		"participant"
	)

    assigned_staff = frappe.get_all(
		"Support Task Assigned Staff",
		filters={
			"parent": task.name,
			"parenttype": "Support Task",
		},
		fields=[
			"staff_user",
			"role",
			"idx",
		],
		order_by="idx asc",
	)

    return {
		"execution_instance": execution.name,
		"support_task": task.name,
		"support_plan": task.support_plan,
		"participant": participant,
		"task_name": task.task_name,
		"task_category": task.task_category,
		"clinical_priority": task.clinical_priority,
		"source_doctype": task.source_doctype,
		"source_docname": task.source_docname,
		"source_row_id": task.source_row_id,
		"assigned_staff": assigned_staff,
		"scheduled_date": execution.scheduled_date,
		"scheduled_time": execution.scheduled_time,
		"status": execution.status,
		"outcome": execution.outcome,
		"exception_type": execution.exception_type,
		"follow_up_required": execution.follow_up_required,
		"executed_by": execution.executed_by,
		"actual_execution_time": execution.actual_execution_time,
		"execution_notes": execution.execution_notes,
	}


# ================================================================
# VALIDATE MANAGER FOLLOW-UP DECISION
# ================================================================

@frappe.whitelist()
def validate_manager_follow_up_decision(
    execution_instance,
    follow_up_action,
    manager_notes=None
):
    """
    Validate and process a manager's execution-review decision.

    Supported actions:

        Acknowledge
        Create Follow-up
        Mark No Follow-up Required

    The execution record remains the authoritative operational record.

    Manager Follow-up is created as a separate management record
    when required.
    """

    if not execution_instance:
        frappe.throw(
            "Execution Instance is required."
        )

    if not follow_up_action:
        frappe.throw(
            "Manager Follow-up Action is required."
        )

    allowed_actions = {
        "Acknowledge",
        "Create Follow-up",
        "Mark No Follow-up Required"
    }

    if follow_up_action not in allowed_actions:
        frappe.throw(
            "Invalid Manager Follow-up Action."
        )

    execution_instance = str(
        execution_instance
    ).strip()

    if not frappe.db.exists(
        "Support Task Execution Instance",
        execution_instance
    ):
        frappe.throw(
            "Execution record not found."
        )

    execution = frappe.get_doc(
        "Support Task Execution Instance",
        execution_instance
    )

    manager_notes = (
        manager_notes or ""
    ).strip()

    follow_up_required = bool(
        getattr(
            execution,
            "follow_up_required",
            0
        )
    )

    # ------------------------------------------------------------
    # ACKNOWLEDGE
    # ------------------------------------------------------------

    if follow_up_action == "Acknowledge":

        return {
            "valid": True,
            "action": "Acknowledge",
            "execution_instance": execution.name,
            "message": "Manager review acknowledged."
        }

    # ------------------------------------------------------------
    # MARK NO FOLLOW-UP REQUIRED
    # ------------------------------------------------------------

    if follow_up_action == "Mark No Follow-up Required":

        # Explicit manager override.
        if hasattr(
            execution,
            "follow_up_required"
        ):
            execution.db_set(
                "follow_up_required",
                0,
                update_modified=True
            )

        return {
            "valid": True,
            "action":
                "Mark No Follow-up Required",
            "execution_instance":
                execution.name,
            "message":
                "Follow-up requirement cleared."
        }

    # ------------------------------------------------------------
    # CREATE FOLLOW-UP
    # ------------------------------------------------------------

    if follow_up_action == "Create Follow-up":

        if not follow_up_required:
            frappe.throw(
                "This execution is not marked as requiring follow-up."
            )

        if not manager_notes:
            frappe.throw(
                "Manager Notes are required when creating a follow-up."
            )

        # --------------------------------------------------------
        # Prevent duplicate active follow-ups.
        # --------------------------------------------------------

        existing = frappe.get_all(
            "Manager Follow-up",
            filters={
                "execution_instance":
                    execution.name,
                "status": [
                    "in",
                    [
                        "Open",
                        "In Progress"
                    ]
                ]
            },
            fields=[
                "name",
                "status",
                "assigned_to",
                "due_date",
                "priority"
            ],
            order_by="modified desc",
            limit_page_length=1
        )

        if existing:

            return {
                "valid": True,
                "action": "Existing Follow-up",
                "execution_instance":
                    execution.name,
                "follow_up":
                    existing[0],
                "message":
                    "An active follow-up already exists."
            }

        return {
            "valid": True,
            "action":
                "Create Follow-up",
            "execution_instance":
                execution.name,
            "follow_up_required":
                1,
            "manager_notes":
                manager_notes,
            "message":
                "Follow-up details are required."
        }


@frappe.whitelist()
def create_manager_follow_up(
    execution_instance,
    follow_up_reason,
    priority,
    description,
    assigned_to,
    due_date,
    due_time=None,
    manager_notes=None
):
    """
    Create a Manager Follow-up from an execution review.

    Prevents duplicate active follow-ups for the same
    execution instance.
    """

    if not execution_instance:
        frappe.throw(
            "Execution Instance is required."
        )

    execution_instance = str(
        execution_instance
    ).strip()

    if not execution_instance:
        frappe.throw(
            "Execution Instance is required."
        )

    if not frappe.db.exists(
        "Support Task Execution Instance",
        execution_instance
    ):
        frappe.throw(
            "Execution record not found."
        )

    if not frappe.has_permission(
        "Manager Follow-up",
        "create"
    ):
        frappe.throw(
            "You do not have permission to create Manager Follow-ups."
        )

    execution = frappe.get_doc(
        "Support Task Execution Instance",
        execution_instance
    )
    support_task = frappe.get_doc(
        "Support Task",
        execution.support_task
    )

    participant = frappe.db.get_value(
        "Support Plan",
        support_task.support_plan,
        "participant"
    )
    if not getattr(
        execution,
        "follow_up_required",
        0
    ):
        frappe.throw(
            "This execution is not marked as requiring follow-up."
        )

    # ------------------------------------------------------------
    # Validate required values.
    # ------------------------------------------------------------

    required_values = {
        "Follow-up Reason":
            follow_up_reason,
        "Priority":
            priority,
        "Description":
            description,
        "Assigned To":
            assigned_to,
        "Due Date":
            due_date
    }

    for label, value in required_values.items():

        if not value or not str(value).strip():
            frappe.throw(
                f"{label} is required."
            )

    # ------------------------------------------------------------
    # Duplicate protection.
    # ------------------------------------------------------------

    existing = frappe.get_all(
        "Manager Follow-up",
        filters={
            "execution_instance":
                execution.name,
            "status": [
                "in",
                [
                    "Open",
                    "In Progress"
                ]
            ]
        },
        fields=[
            "name",
            "status",
            "assigned_to",
            "due_date",
            "priority"
        ],
        order_by="modified desc",
        limit_page_length=1
    )

    if existing:

        return {
            "created": False,
            "duplicate": True,
            "follow_up":
                existing[0],
            "message":
                "An active follow-up already exists."
        }

    # ------------------------------------------------------------
    # Create Manager Follow-up.
    # ------------------------------------------------------------
    task = frappe.get_doc(
        "Support Task",
        execution.support_task
    )

    participant = frappe.db.get_value(
        "Support Plan",
        task.support_plan,
        "participant"
    )
    follow_up = frappe.get_doc({
        "doctype":
            "Manager Follow-up",

        "execution_instance":
            execution.name,

        "support_task":
            execution.support_task,

        "participant":
            participant,

        "follow_up_reason":
            follow_up_reason,

        "priority":
            priority,

        "description":
            description,

        "assigned_to":
            assigned_to,

        "due_date":
            due_date,

        "due_time":
            due_time,

        "status":
            "Open",

        "manager_notes":
            manager_notes or "",

        "created_from_dashboard":
            1
    })

    follow_up.insert(
        ignore_permissions=False
    )

    frappe.db.commit()

    return {
        "created": True,
        "duplicate": False,
        "follow_up": {
            "name":
                follow_up.name,

            "status":
                follow_up.status,

            "assigned_to":
                follow_up.assigned_to,

            "due_date":
                follow_up.due_date,

            "due_time":
                follow_up.due_time,

            "priority":
                follow_up.priority
        },

        "message":
            "Manager Follow-up created successfully."
    }




@frappe.whitelist()
def get_manager_follow_ups(
	status=None,
	start_date=None,
	end_date=None,
	assigned_to=None,
	participant=None,
	limit=50
):
	"""
	Return active Manager Follow-up records for the Manager Dashboard.

	Only Open and In Progress follow-ups are returned by default.
	Supports filtering by participant and assigned staff cleanly.

	Frappe v16 compatible.
	"""

	if not frappe.has_permission(
		"Manager Follow-up",
		"read"
	):
		frappe.throw(
			"You do not have permission to view Manager Follow-ups."
		)

	# ------------------------------------------------------------
	# Safe limit
	# ------------------------------------------------------------

	try:
		limit = int(limit)
	except (TypeError, ValueError):
		limit = 50

	limit = max(
		1,
		min(
			limit,
			100
		)
	)

	# ------------------------------------------------------------
	# Status
	# ------------------------------------------------------------

	if status and str(status).strip():

		allowed_statuses = {
			"Open",
			"In Progress",
			"Resolved",
			"Cancelled"
		}

		if status not in allowed_statuses:
			frappe.throw(
				"Invalid follow-up status."
			)

		status_filter = status

	else:

		status_filter = [
			"in",
			[
				"Open",
				"In Progress"
			]
		]

	# ------------------------------------------------------------
	# Filters
	# ------------------------------------------------------------

	filters = {
		"status": status_filter
	}

	# Clean string parameters passed from front-end filters
	if assigned_to and str(assigned_to).strip():
		filters["assigned_to"] = str(assigned_to).strip()

	if participant and str(participant).strip():
		filters["participant"] = str(participant).strip()

	if start_date and end_date:

		filters["due_date"] = [
			"between",
			[
				start_date,
				end_date
			]
		]

	elif start_date:

		filters["due_date"] = [
			">=",
			start_date
		]

	elif end_date:

		filters["due_date"] = [
			"<=",
			end_date
		]

	# ------------------------------------------------------------
	# Query (Frappe v16 safe ordering without FIELD())
	# ------------------------------------------------------------

	return frappe.get_all(
		"Manager Follow-up",

		filters=filters,

		fields=[
			"name",
			"execution_instance",
			"support_task",
			"participant",
			"follow_up_reason",
			"priority",
			"description",
			"assigned_to",
			"due_date",
			"due_time",
			"status",
			"resolution",
			"resolved_on",
			"resolved_by",
			"manager_notes",
			"created_from_dashboard"
		],

		order_by="""
			due_date asc,
			due_time asc,
			modified desc
		""",

		limit_page_length=limit
	)

@frappe.whitelist()
def update_manager_follow_up(
    follow_up_name,
    status=None,
    assigned_to=None,
    due_date=None,
    due_time=None,
    manager_notes=None,
    resolution=None
):
    """
    Update an existing Manager Follow-up.
    """

    if not follow_up_name:
        frappe.throw(
            "Follow-up is required."
        )

    if not frappe.db.exists(
        "Manager Follow-up",
        follow_up_name
    ):
        frappe.throw(
            "Manager Follow-up not found."
        )

    if not frappe.has_permission(
        "Manager Follow-up",
        "write"
    ):
        frappe.throw(
            "You do not have permission to update Manager Follow-ups."
        )

    follow_up = frappe.get_doc(
        "Manager Follow-up",
        follow_up_name
    )

    if status:
        allowed_statuses = {
            "Open",
            "In Progress",
            "Resolved",
            "Cancelled"
        }

        if status not in allowed_statuses:
            frappe.throw(
                "Invalid Follow-up Status."
            )

        follow_up.status = status

    if assigned_to is not None:
        follow_up.assigned_to = assigned_to

    if due_date is not None:
        follow_up.due_date = due_date

    if due_time is not None:
        follow_up.due_time = due_time

    if manager_notes is not None:
        follow_up.manager_notes = (
            manager_notes or ""
        ).strip()

    if resolution is not None:
        follow_up.resolution = (
            resolution or ""
        ).strip()

    # ------------------------------------------------------------
    # Resolution rules.
    # ------------------------------------------------------------

    if follow_up.status == "Resolved":

        if not follow_up.resolution:
            frappe.throw(
                "Resolution is required before resolving a follow-up."
            )

        follow_up.resolved_on = (
            frappe.utils.now_datetime()
        )

        follow_up.resolved_by = (
            frappe.session.user
        )

    else:

        follow_up.resolved_on = None
        follow_up.resolved_by = None

    follow_up.save(
        ignore_permissions=False
    )

    frappe.db.commit()

    return {
        "updated": True,
        "follow_up": {
            "name":
                follow_up.name,
            "status":
                follow_up.status,
            "assigned_to":
                follow_up.assigned_to,
            "due_date":
                follow_up.due_date,
            "due_time":
                follow_up.due_time,
            "resolution":
                follow_up.resolution,
            "resolved_on":
                follow_up.resolved_on,
            "resolved_by":
                follow_up.resolved_by
        }
    }


# ================================================================
# KPI CALCULATION
# ================================================================

def calculate_kpis(
    reviews
):
    """
    Calculate dashboard KPIs from execution/review records.

    This function is intentionally isolated so that future phases
    can replace the underlying query with optimized database
    aggregation without changing the dashboard UI.
    """

    kpis = {

        "total":
            0,

        "completed":
            0,

        "missed":
            0,

        "exceptions":
            0,

        "follow_up":
            0,

        "in_progress":
            0

    }


    for row in reviews:

        kpis["total"] += 1


        review_category = (
            row.get(
                "review_category"
            )
            or ""
        )


        status_value = (
            row.get(
                "status"
            )
            or ""
        )


        # --------------------------------------------------------
        # Completed
        # --------------------------------------------------------

        if (
            review_category == "Completed"
        ):

            kpis["completed"] += 1


        # --------------------------------------------------------
        # Missed
        # --------------------------------------------------------

        if (
            review_category == "Missed"
        ):

            kpis["missed"] += 1


        # --------------------------------------------------------
        # Exception
        # --------------------------------------------------------

        if (
            review_category == "Exception"
        ):

            kpis["exceptions"] += 1


        # --------------------------------------------------------
        # Follow-up
        # --------------------------------------------------------

        if (
            row.get(
                "follow_up_required"
            )
        ):

            kpis["follow_up"] += 1


        # --------------------------------------------------------
        # In Progress
        # --------------------------------------------------------

        if (
            status_value == "In Progress"
        ):

            kpis["in_progress"] += 1


    return kpis


# ================================================================
# EXISTING MANAGER REVIEW SOURCE
# ================================================================
# ================================================================
# ================================================================
# NEEDS ATTENTION
# ================================================================

@frappe.whitelist()
def get_manager_attention_items(
    start_date=None,
    end_date=None,
    attention_type=None,
    limit=50,
    participant=None
):
    """
    Return execution records requiring manager attention.

    Phase 3B.4 adds controlled attention filtering.

    Supported attention_type values:

        all
        follow_up
        missed
        exception

    This remains a derived view. No new DocType is introduced.

    `participant` is an optional Participant Profile filter applied
    through the existing backend query architecture (Change 1 —
    Manager Dashboard Participant Filter). Leaving it empty preserves
    the exact existing behaviour.
    """

    if not start_date:

        start_date = frappe.utils.today()

    if not end_date:

        end_date = start_date

    if start_date > end_date:

        frappe.throw(
            "Start Date cannot be after End Date."
        )

    try:

        limit = int(
            limit
        )

    except (
        TypeError,
        ValueError
    ):

        limit = 50

    limit = max(
        1,
        min(
            limit,
            100
        )
    )

    attention_type = (
        attention_type
        or "all"
    ).strip().lower()

    allowed_types = {

        "all",

        "follow_up",

        "missed",

        "exception"

    }

    if attention_type not in allowed_types:

        frappe.throw(
            "Invalid attention type."
        )

    reviews = get_manager_review_tasks(
        start_date=start_date,
        end_date=end_date,
        participant=participant
    )

    reviews = reviews or []

    attention_items = []

    for row in reviews:

        follow_up_required = bool(
            row.get(
                "follow_up_required"
            )
        )

        review_category = (
            row.get(
                "review_category"
            )
            or ""
        )

        review_priority = (
            row.get(
                "review_priority"
            )
            or "Low"
        )

        # --------------------------------------------------------
        # Determine whether this record requires attention
        # --------------------------------------------------------

        needs_attention = (

            follow_up_required

            or

            review_category in (
                "Missed",
                "Exception"
            )

            or

            review_priority == "High"

        )

        if not needs_attention:

            continue

        # --------------------------------------------------------
        # Apply attention-type filter
        # --------------------------------------------------------

        if attention_type == "follow_up":

            if not follow_up_required:

                continue

        elif attention_type == "missed":

            if review_category != "Missed":

                continue

        elif attention_type == "exception":

            if review_category != "Exception":

                continue

        # --------------------------------------------------------
        # Build attention reasons
        # --------------------------------------------------------

        attention_reason = []

        if follow_up_required:

            attention_reason.append(
                "Follow-up Required"
            )

        if review_category == "Missed":

            attention_reason.append(
                "Missed Task"
            )

        if review_category == "Exception":

            attention_reason.append(
                "Exception"
            )

        if review_priority == "High":

            attention_reason.append(
                "High Priority"
            )

        item = dict(
            row
        )

        item["attention_reason"] = (
            ", ".join(
                attention_reason
            )
        )

        item["follow_up_status"] = (

            "Required"

            if follow_up_required

            else

            "Not Required"

        )

        attention_items.append(
            item
        )

    # ------------------------------------------------------------
    # Priority ordering
    # ------------------------------------------------------------

    priority_order = {

        "High": 1,

        "Medium": 2,

        "Low": 3

    }

    attention_items.sort(
        key=lambda row: (

            priority_order.get(
                row.get(
                    "review_priority"
                ),
                99
            ),

            row.get(
                "scheduled_date"
            ) or "",

            row.get(
                "scheduled_time"
            ) or ""

        )
    )

    return attention_items[
        :limit
    ]
def get_manager_review_tasks(
    start_date=None,
    end_date=None,
    status=None,
    follow_up_required=None,
    participant=None
):
    """
    Use the existing Manager Review implementation from the
    Support Task Schedule module.

    We deliberately reuse the existing business logic so that
    Manager Dashboard and Support Task Schedule do not develop
    different interpretations of task execution.

    `participant` is forwarded straight through to the existing
    Support Task Schedule query, which already applies it as a
    `sp.participant = %(participant)s` SQL condition (Change 1).
    """

    from care_management.care_management.page.support_task_schedule import (
        support_task_schedule
    )


    return (
        support_task_schedule
        .get_manager_review_tasks(
            start_date=start_date,
            end_date=end_date,
            status=status,
            follow_up_required=follow_up_required,
            participant=participant
        )
    )