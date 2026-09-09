frappe.ui.form.on("Medication PRN Effectiveness Review", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query: "care_management.care_management.doctype.medication_prn_effectiveness_review.medication_prn_effectiveness_review.search_medication_prn_review_participants",
		}));
		frm.set_query("medication_event", () => ({
			query: "care_management.care_management.doctype.medication_prn_effectiveness_review.medication_prn_effectiveness_review.search_medication_prn_review_events",
		}));
		frm.set_query("medication_plan", () => ({
			query: "care_management.care_management.doctype.medication_prn_effectiveness_review.medication_prn_effectiveness_review.search_medication_prn_review_plans",
		}));
	},
});
