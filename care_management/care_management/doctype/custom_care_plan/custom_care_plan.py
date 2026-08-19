# care_management/care_management/doctype/custom_care_plan/custom_care_plan.py

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today, now_datetime

from care_management.care_management.services.custom_plan_sync_engine import (
    CustomPlanSyncEngine,
)


class CustomCarePlan(Document):

    def validate(self):
        self.validate_dates()
        self.validate_participant()
        self.validate_activities()
        self.validate_lifecycle_edit_rules()

    def on_update(self):
        """
        Synchronize an Active plan after normal edits.

        Lifecycle methods can explicitly skip this hook when they already
        perform the required synchronization/deactivation operation.
        """
        if (
            self.status == "Active"
            and not self.flags.get("skip_custom_plan_sync")
        ):
            CustomPlanSyncEngine(self).sync()

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def validate_dates(self):
        if not self.start_date:
            frappe.throw(_("Start Date is required."))

        if self.end_date and getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_("End Date cannot be before Start Date."))

    def validate_participant(self):
        if not self.participant:
            return

        participant_doctype = "Participant Profile"

        if not frappe.db.exists("DocType", participant_doctype):
            return

        meta = frappe.get_meta(participant_doctype)

        status_field = None

        for candidate in (
            "status",
            "participant_status",
            "workflow_state",
        ):
            if meta.has_field(candidate):
                status_field = candidate
                break

        if not status_field:
            return

        participant_status = frappe.db.get_value(
            participant_doctype,
            self.participant,
            status_field,
        )

        if participant_status in {
            "Inactive",
            "Archived",
            "Deceased",
            "Suspended",
        }:
            frappe.throw(
                _(
                    "Cannot create or modify a care plan for inactive "
                    "participant '{0}' (Status: {1})."
                ).format(
                    self.participant,
                    participant_status,
                )
            )

    def validate_activities(self):
        if not self.activities:
            frappe.throw(
                _("A Custom Care Plan must contain at least one activity.")
            )

        for idx, row in enumerate(self.activities, start=1):

            if not row.activity_name:
                frappe.throw(
                    _("Row #{0}: Activity Name is required.").format(idx)
                )

            if not row.activity_category:
                frappe.throw(
                    _("Row #{0}: Activity Category is required.").format(idx)
                )

            if not row.frequency:
                frappe.throw(
                    _("Row #{0}: Frequency is required.").format(idx)
                )

            if not row.scheduled_time:
                frappe.throw(
                    _("Row #{0}: Scheduled Time is required.").format(idx)
                )

            if (
                row.expected_duration_minutes is not None
                and row.expected_duration_minutes != ""
            ):
                try:
                    duration = int(row.expected_duration_minutes)
                except (TypeError, ValueError):
                    frappe.throw(
                        _(
                            "Row #{0}: Expected Duration must be a valid "
                            "number."
                        ).format(idx)
                    )

                if duration <= 0:
                    frappe.throw(
                        _(
                            "Row #{0}: Expected Duration must be greater "
                            "than 0 minutes."
                        ).format(idx)
                    )

            if row.staff_count_required is not None:
                try:
                    staff_count = int(row.staff_count_required)
                except (TypeError, ValueError):
                    frappe.throw(
                        _(
                            "Row #{0}: Staff Count Required must be a "
                            "valid number."
                        ).format(idx)
                    )

                if staff_count <= 0:
                    frappe.throw(
                        _(
                            "Row #{0}: Staff Count Required must be "
                            "greater than 0."
                        ).format(idx)
                    )

            if row.frequency in {"Weekly", "Specific Days"}:
                if not row.days_of_week:
                    frappe.throw(
                        _(
                            "Row #{0}: Please specify days of the week "
                            "for frequency '{1}'."
                        ).format(
                            idx,
                            row.frequency,
                        )
                    )

                self._validate_days_of_week(
                    row.days_of_week,
                    idx,
                )

            if row.frequency == "Monthly":
                if not row.day_of_month:
                    frappe.throw(
                        _(
                            "Row #{0}: Day of Month is required for "
                            "Monthly frequency."
                        ).format(idx)
                    )

                try:
                    day = int(row.day_of_month)
                except (TypeError, ValueError):
                    frappe.throw(
                        _(
                            "Row #{0}: Day of Month must be a number "
                            "between 1 and 31."
                        ).format(idx)
                    )

                if not 1 <= day <= 31:
                    frappe.throw(
                        _(
                            "Row #{0}: Day of Month must be between "
                            "1 and 31."
                        ).format(idx)
                    )

    @staticmethod
    def _validate_days_of_week(value, row_number):
        allowed = {
            "Mon",
            "Tue",
            "Wed",
            "Thu",
            "Fri",
            "Sat",
            "Sun",
        }

        supplied = [
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        ]

        invalid = [
            item
            for item in supplied
            if item not in allowed
        ]

        if invalid:
            frappe.throw(
                _(
                    "Row #{0}: Invalid day(s): {1}. "
                    "Use Mon, Tue, Wed, Thu, Fri, Sat, Sun."
                ).format(
                    row_number,
                    ", ".join(invalid),
                )
            )

    def validate_lifecycle_edit_rules(self):
        if self.is_new():
            return

        original_status = frappe.db.get_value(
            self.doctype,
            self.name,
            "status",
        )

        original_participant = frappe.db.get_value(
            self.doctype,
            self.name,
            "participant",
        )

        if original_status in {
            "Active",
            "Deactivated",
            "Expired",
        }:
            if (
                original_participant
                and self.participant != original_participant
            ):
                frappe.throw(
                    _(
                        "Participant cannot be modified once the plan "
                        "has moved out of Draft status."
                    )
                )

    # -------------------------------------------------------------------------
    # DELETE PROTECTION
    # -------------------------------------------------------------------------

    def on_trash(self):
        if self.status not in {
            "Active",
            "Deactivated",
            "Expired",
        }:
            return

        if not frappe.db.exists(
            "DocType",
            "Support Task",
        ):
            return

        linked_tasks = frappe.get_all(
            "Support Task",
            filters={
                "source_doctype": "Custom Care Plan",
                "source_docname": self.name,
            },
            pluck="name",
        )

        if not linked_tasks:
            return

        if not frappe.db.exists(
            "DocType",
            "Support Task Execution Instance",
        ):
            return

        historical_statuses = [
            "Completed",
            "Partially Completed",
            "In Progress",
            "Refused",
            "Missed",
        ]

        has_historical_execution = frappe.db.exists(
            "Support Task Execution Instance",
            {
                "support_task": ["in", linked_tasks],
                "status": ["in", historical_statuses],
            },
        )

        if has_historical_execution:
            frappe.throw(
                _(
                    "Cannot delete this Care Plan because historical "
                    "execution records exist. Deactivate the plan instead "
                    "to maintain audit compliance."
                )
            )

    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------

    @frappe.whitelist()
    def submit_for_review(self):
        self._check_lifecycle_permission()

        if self.status != "Draft":
            frappe.throw(
                _("Only Draft plans can be submitted for review.")
            )

        self.status = "Pending Review"

        self.flags.skip_custom_plan_sync = True
        self.save()

        return {
            "status": self.status,
        }

    @frappe.whitelist()
    def activate_plan(self):
        self._check_lifecycle_permission()

        if self.status not in {
            "Draft",
            "Pending Review",
        }:
            frappe.throw(
                _(
                    "Only Draft or Pending Review plans can be activated."
                )
            )

        if self.end_date and getdate(self.end_date) < getdate(today()):
            frappe.throw(
                _(
                    "Cannot activate an expired plan. "
                    "End Date is in the past."
                )
            )

        if not self.activities:
            frappe.throw(
                _("A Custom Care Plan must contain at least one activity.")
            )

        self.status = "Active"
        self.activated_by = frappe.session.user
        self.activated_on = now_datetime()

        # Prevent on_update() from performing the same sync again.
        self.flags.skip_custom_plan_sync = True
        self.save()

        # One and only one explicit synchronization.
        CustomPlanSyncEngine(self).sync()

        frappe.msgprint(
            _(
                "Custom Care Plan '{0}' activated successfully."
            ).format(self.plan_name),
            alert=True,
        )

        return {
            "status": self.status,
        }

    @frappe.whitelist()
    def deactivate_plan(self, reason=None):
        self._check_lifecycle_permission()

        if self.status != "Active":
            frappe.throw(
                _("Only Active plans can be deactivated.")
            )

        reason = (reason or "").strip()

        if not reason:
            frappe.throw(
                _(
                    "A deactivation reason is required for "
                    "compliance audit."
                )
            )

        self.status = "Deactivated"
        self.deactivated_by = frappe.session.user
        self.deactivated_on = now_datetime()
        self.deactivation_reason = reason

        # Do not run normal Active-plan sync during save.
        self.flags.skip_custom_plan_sync = True
        self.save()

        CustomPlanSyncEngine(self).deactivate_all_schedules(
            reason=reason
        )

        frappe.msgprint(
            _(
                "Custom Care Plan '{0}' has been deactivated."
            ).format(self.plan_name),
            alert=True,
        )

        return {
            "status": self.status,
        }

    # -------------------------------------------------------------------------
    # PERMISSIONS
    # -------------------------------------------------------------------------

    def _check_lifecycle_permission(self):
        allowed_roles = {
            "Care Manager",
            "System Manager",
            "Administrator",
        }

        user_roles = set(
            frappe.get_roles(frappe.session.user)
        )

        if not user_roles.intersection(allowed_roles):
            frappe.throw(
                _(
                    "Only Care Managers or System Managers are "
                    "authorized to change the lifecycle state of "
                    "a Care Plan."
                ),
                frappe.PermissionError,
            )