// Copyright (c) 2026, Hex Flow and contributors
// For license information, please see license.txt

frappe.ui.form.on("Medication Administration Event", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_participants",
		}));
		frm.set_query("medication_plan", () => ({
			query:
				"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_plans",
		}));
		frm.set_query("support_task", () => ({
			query:
				"care_management.care_management.doctype.medication_administration_event.medication_administration_event.search_medication_event_support_tasks",
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Create Addendum"), () => {
			const event_name = frm.doc.name;
			frappe.new_doc("Medication Event Addendum").then(() => {
				if (cur_frm?.doctype === "Medication Event Addendum") {
					cur_frm.set_value("medication_event", event_name);
				}
			});
		});
	},
});
