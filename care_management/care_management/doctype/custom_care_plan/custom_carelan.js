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
        const color = status_color_map[frm.doc.status] || "gray";
        frm.page.set_indicator(__(frm.doc.status), color);
    },

    setup_action_buttons(frm) {
        if (frm.is_new()) return;

        // Draft State Actions
        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__("Submit for Review"), () => {
                frappe.call({
                    method: "submit_for_review",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Submitting for review..."),
                    callback(r) {
                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));

            frm.add_custom_button(__("Activate Plan"), () => {
                frm.trigger("confirm_and_activate");
            }).addClass("btn-primary");
        }

        // Pending Review State Actions
        if (frm.doc.status === "Pending Review") {
            frm.add_custom_button(__("Activate Plan"), () => {
                frm.trigger("confirm_and_activate");
            }).addClass("btn-primary");
        }

        // Active State Actions
        if (frm.doc.status === "Active") {
            frm.add_custom_button(__("Deactivate Plan"), () => {
                frm.trigger("prompt_deactivation_reason");
            }).addClass("btn-danger");

            frm.add_custom_button(__("View Operational Tasks"), () => {
                frappe.set_route("List", "Support Task", {
                    source_doctype: "Custom Care Plan",
                    source_docname: frm.doc.name
                });
            }, __("Navigation"));
        }

        // Deactivated State Actions
        if (frm.doc.status === "Deactivated") {
            frm.add_custom_button(__("Reactivate Plan"), () => {
                frm.trigger("confirm_and_activate");
            }, __("Actions"));
        }
    },

    confirm_and_activate(frm) {
        frappe.confirm(
            __("Activating <b>{0}</b> will immediately generate Support Tasks and schedule rules for staff execution. Proceed?", [frm.doc.plan_name]),
            () => {
                frappe.call({
                    method: "activate_plan",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Activating plan & scheduling tasks..."),
                    callback(r) {
                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    },

    prompt_deactivation_reason(frm) {
        const dialog = new frappe.ui.Dialog({
            title: __("Deactivate Custom Care Plan"),
            fields: [
                {
                    label: __("Reason for Deactivation"),
                    fieldname: "reason",
                    fieldtype: "Small Text",
                    reqd: 1,
                    description: __("Provide a clear reason for audit and compliance.")
                }
            ],
            primary_action_label: __("Confirm Deactivation"),
            primary_action(values) {
                dialog.hide();
                frappe.call({
                    method: "deactivate_plan",
                    doc: frm.doc,
                    args: {
                        reason: values.reason
                    },
                    freeze: true,
                    freeze_message: __("Deactivating plan & disabling future schedules..."),
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

    setup_dashboard_connections(frm) {
        if (frm.is_new() || frm.doc.status === "Draft") return;

        // Query counts for generated tasks and execution logs
        frappe.call({
            method: "frappe.client.get_count",
            args: {
                doctype: "Support Task",
                filters: {
                    source_doctype: "Custom Care Plan",
                    source_docname: frm.doc.name
                }
            },
            callback(r) {
                const task_count = r.message || 0;
                frm.dashboard.clear_headline();
                frm.dashboard.add_indicator(
                    __("Active Support Tasks: {0}", [task_count]),
                    task_count > 0 ? "blue" : "gray"
                );
            }
        });
    }
});

// Grid Validation & Child Table Field Listeners
frappe.ui.form.on("Custom Care Plan Activity", {
    frequency(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.frequency === "Daily") {
            frappe.model.set_value(cdt, cdn, "days_of_week", "");
            frappe.model.set_value(cdt, cdn, "day_of_month", null);
        } else if (row.frequency === "Monthly") {
            frappe.model.set_value(cdt, cdn, "days_of_week", "");
        }
    },

    expected_duration_minutes(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.expected_duration_minutes <= 0) {
            frappe.msgprint(__("Duration must be a positive integer."));
            frappe.model.set_value(cdt, cdn, "expected_duration_minutes", 30);
        }
    }
});