frappe.ui.form.on("Discarded Medication Register", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.discarded_medication_register.discarded_medication_register.search_discarded_medication_participants",
		}));
	},
});
