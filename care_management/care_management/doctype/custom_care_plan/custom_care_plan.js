// care_management/care_management/doctype/custom_care_plan/custom_care_plan.js

frappe.ui.form.on("Custom Care Plan", {

    refresh(frm) {
        frm.trigger("setup_status_indicator");
        frm.trigger("setup_action_buttons");
        frm.trigger("setup_dashboard_connections");
    },

    setup_status_indicator(frm) {
        const status_color_map = {
            "Draft": "gray",
            "Pending Review": "orange",
            "Active": "green",
            "Deactivated": "red",
            "Expired": "darkgrey"
        };

        const status = frm.doc.status || "Draft";
        const color = status_color_map[status] || "gray";

        frm.page.set_indicator(
            __(status),
            color
        );
    },

    setup_action_buttons(frm) {
        frm.clear_custom_buttons();

        if (
            frm.is_new() ||
            frm.is_dirty()
        ) {
            return;
        }

        // -------------------------------------------------------------
        // DRAFT
        // -------------------------------------------------------------

        if (frm.doc.status === "Draft") {

            frm.add_custom_button(
                __("Activate Plan"),
                () => {
                    frm.trigger("confirm_and_activate");
                }
            ).addClass("btn-primary");

            frm.page.add_inner_button(
                __("Submit for Review"),
                () => {
                    frappe.call({
                        method: "submit_for_review",
                        doc: frm.doc,
                        freeze: true,
                        freeze_message: __(
                            "Submitting plan for review..."
                        ),

                        callback(r) {
                            if (!r.exc) {
                                frm.reload_doc();
                            }
                        }
                    });
                },
                __("Actions")
            );
        }

        // -------------------------------------------------------------
        // PENDING REVIEW
        // -------------------------------------------------------------

        else if (
            frm.doc.status === "Pending Review"
        ) {

            frm.add_custom_button(
                __("Activate Plan"),
                () => {
                    frm.trigger("confirm_and_activate");
                }
            ).addClass("btn-primary");
        }

        // -------------------------------------------------------------
        // ACTIVE
        // -------------------------------------------------------------

        else if (
            frm.doc.status === "Active"
        ) {

            frm.add_custom_button(
                __("Deactivate Plan"),
                () => {
                    frm.trigger(
                        "prompt_deactivation_reason"
                    );
                }
            ).addClass("btn-danger");

            frm.page.add_inner_button(
                __("View Operational Tasks"),
                () => {
                    frappe.set_route(
                        "List",
                        "Support Task",
                        {
                            source_doctype:
                                "Custom Care Plan",

                            source_docname:
                                frm.doc.name
                        }
                    );
                },
                __("Navigation")
            );
        }

        // -------------------------------------------------------------
        // DEACTIVATED
        // -------------------------------------------------------------

        else if (
            frm.doc.status === "Deactivated"
        ) {

            frm.page.add_inner_button(
                __("View Historical Tasks"),
                () => {
                    frappe.set_route(
                        "List",
                        "Support Task",
                        {
                            source_doctype:
                                "Custom Care Plan",

                            source_docname:
                                frm.doc.name
                        }
                    );
                },
                __("Navigation")
            );
        }
    },

    // -----------------------------------------------------------------
    // ACTIVATE
    // -----------------------------------------------------------------

    confirm_and_activate(frm) {

        if (
            frm.is_dirty()
        ) {
            frappe.msgprint({
                title: __("Save Required"),
                message: __(
                    "Please save the Care Plan before activating it."
                ),
                indicator: "orange"
            });

            return;
        }

        frappe.confirm(
            __(
                "Activating <b>{0}</b> will create or synchronize " +
                "the operational Support Tasks and schedule rules. " +
                "Proceed?",
                [frm.doc.plan_name]
            ),

            () => {

                frappe.call({
                    method: "activate_plan",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __(
                        "Activating plan and synchronizing operational tasks..."
                    ),

                    callback(r) {

                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    },

    // -----------------------------------------------------------------
    // DEACTIVATE
    // -----------------------------------------------------------------

    prompt_deactivation_reason(frm) {

        const dialog = new frappe.ui.Dialog({
            title: __(
                "Deactivate Custom Care Plan"
            ),

            fields: [
                {
                    label: __(
                        "Reason for Deactivation"
                    ),

                    fieldname: "reason",

                    fieldtype: "Small Text",

                    reqd: 1,

                    description: __(
                        "Provide a clear reason for audit and compliance."
                    )
                }
            ],

            primary_action_label: __(
                "Confirm Deactivation"
            ),

            primary_action(values) {

                const reason =
                    (values.reason || "").trim();

                if (!reason) {
                    frappe.msgprint({
                        title: __("Reason Required"),
                        message: __(
                            "A deactivation reason is required."
                        ),
                        indicator: "red"
                    });

                    return;
                }

                dialog.hide();

                frappe.call({
                    method: "deactivate_plan",

                    doc: frm.doc,

                    args: {
                        reason: reason
                    },

                    freeze: true,

                    freeze_message: __(
                        "Deactivating plan and cancelling eligible future executions..."
                    ),

                    callback(r) {

                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }
        });

        dialog.show();
    },

    // -----------------------------------------------------------------
    // DASHBOARD
    // -----------------------------------------------------------------

    
    setup_dashboard_connections(frm) {

        if (frm.is_new()) {
            return;
        }

        // The Support Task schema is the source of truth.
        // Do not assume optional fields such as is_active exist.
        const support_task_meta = frappe.get_meta("Support Task");

        const filters = {
            source_doctype: "Custom Care Plan",
            source_docname: frm.doc.name
        };

        // Only use is_active if the actual Support Task DocType
        // contains that field.
        if (support_task_meta.has_field("is_active")) {
            filters.is_active = 1;
        }

        frappe.call({
            method: "frappe.client.get_count",

            args: {
                doctype: "Support Task",
                filters: filters
            },

            callback(r) {

                if (r.exc) {
                    return;
                }

                const task_count = cint(r.message || 0);

                frm.dashboard.clear_headline();

                frm.dashboard.add_indicator(
                    __("Support Tasks: {0}", [task_count]),
                    task_count > 0 ? "blue" : "gray"
                );
            }
        });
    }
});


// =====================================================================
// CUSTOM CARE PLAN ACTIVITY
// =====================================================================

frappe.ui.form.on(
    "Custom Care Plan Activity",
    {

        frequency(frm, cdt, cdn) {

            const row =
                locals[cdt][cdn];

            if (!row) {
                return;
            }

            if (
                row.frequency === "Daily"
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "days_of_week",
                    ""
                );

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "day_of_month",
                    null
                );
            }

            else if (
                row.frequency === "Weekly"
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "day_of_month",
                    null
                );
            }

            else if (
                row.frequency === "Specific Days"
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "day_of_month",
                    null
                );
            }

            else if (
                row.frequency === "Monthly"
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "days_of_week",
                    ""
                );
            }

            else if (
                row.frequency === "As Needed"
            ) {

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "days_of_week",
                    ""
                );

                frappe.model.set_value(
                    cdt,
                    cdn,
                    "day_of_month",
                    null
                );
            }
        }
    }
);