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
});
