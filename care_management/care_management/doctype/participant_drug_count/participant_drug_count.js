frappe.ui.form.on("Participant Drug Count", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query: "care_management.care_management.doctype.participant_drug_count.participant_drug_count.search_participant_drug_count_participants",
		}));
	},
});
