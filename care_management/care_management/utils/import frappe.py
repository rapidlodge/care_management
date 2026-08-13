import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

# Map Task Categories to their respective Source DocTypes and Child Tables
CATEGORY_SOURCE_MAP = {
    "Meals": {
        "doctype": "Weekly Meal Planner",
        "child_table": "weekly_meal_plan_items",
        "time_field": "meal_time",
        "task_name_field": "meal_type",
        "details_field": "description"
    },
    "Epilepsy / Clinical": {
        "doctype": "Epilepsy Management Plan",
        "child_table": "risk_reduction_items",
        "time_field": "scheduled_time",
        "task_name_field": "measure",
        "details_field": "action_required"
    },
    "Falls / Mobility": {
        "doctype": "Falls Risk Plan",
        "child_table": "review_entries",
        "time_field": "review_time",
        "task_name_field": "review_type",
        "details_field": "notes"
    },
    "Appointments": {
        "doctype": "Appointment Schedule",
        "child_table": "appointment_items",
        "time_field": "appointment_time",
        "task_name_field": "title",
        "details_field": "description"
    }
}

def sync_support_plan_tasks(support_plan_doc):
    """
    Reads linked master source documents on the Support Plan,
    filters by Task Category, and projects scheduled tasks into the Support Task table.
    """
    if not support_plan_doc.participant:
        return

    generated_tasks = 0

    for category, config in CATEGORY_SOURCE_MAP.items():
        # Check if the Support Plan links a document for this category
        source_fieldname = config["doctype"].lower().replace(" ", "_")
        if not hasattr(support_plan_doc, source_fieldname):
            continue

        source_docname = getattr(support_plan_doc, source_fieldname, None)
        if not source_docname:
            continue

        # Fetch the master source document
        if not frappe.db.exists(config["doctype"], source_docname):
            continue

        source_doc = frappe.get_doc(config["doctype"], source_docname)
        child_items = getattr(source_doc, config["child_table"], [])

        for item in child_items:
            task_name = getattr(item, config["task_name_field"], f"{category} Task")
            scheduled_time = getattr(item, config["time_field"], None)
            details = getattr(item, config["details_field"], "")

            # Avoid duplicates if a task with this exact source reference already exists
            existing = frappe.db.exists("Support Task", {
                "participant": support_plan_doc.participant,
                "source_doctype": config["doctype"],
                "source_docname": source_docname,
                "source_child_id": item.name,
                "status": ["in", ["Pending", "In Progress"]]
            })

            if not existing:
                task = frappe.get_doc({
                    "doctype": "Support Task",
                    "participant": support_plan_doc.participant,
                    "support_plan": support_plan_doc.name,
                    "task_category": category,
                    "task_name": task_name,
                    "scheduled_time": scheduled_time,
                    "description": details,
                    "status": "Pending",
                    "source_doctype": config["doctype"],
                    "source_docname": source_docname,
                    "source_child_id": item.name
                })
                task.insert(ignore_permissions=True)
                generated_tasks += 1

    if generated_tasks > 0:
        frappe.msgprint(_("Successfully projected {0} tasks from source plans.").format(generated_tasks), alert=True)