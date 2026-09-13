// Copyright (c) 2026, Hex Flow and contributors
// For license information, please see license.txt

frappe.ui.form.on("Medication Administration Log", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.medication_administration_log.medication_administration_log.search_medication_log_participants",
		}));
	},
});
