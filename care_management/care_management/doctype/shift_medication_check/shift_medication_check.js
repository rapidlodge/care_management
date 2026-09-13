frappe.ui.form.on("Shift Medication Check", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.shift_medication_check.shift_medication_check.search_shift_medication_check_participants",
		}));
		frm.set_query("reconciliation", () => ({
			query:
				"care_management.care_management.doctype.shift_medication_check.shift_medication_check.search_shift_medication_check_reconciliations",
			filters: {
				participant: frm.doc.participant,
			},
		}));
	},
});
