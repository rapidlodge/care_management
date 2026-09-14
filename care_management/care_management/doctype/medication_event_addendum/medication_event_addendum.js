frappe.ui.form.on("Medication Event Addendum", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query: "care_management.care_management.doctype.medication_event_addendum.medication_event_addendum.search_medication_event_addendum_participants",
		}));
		frm.set_query("medication_event", () => ({
			query: "care_management.care_management.doctype.medication_event_addendum.medication_event_addendum.search_medication_event_addendum_events",
		}));
	},
	refresh(frm) {
		[
			"participant",
			"medication_plan",
			"medication_plan_item",
			"event_worker",
			"event_scheduled_datetime",
			"event_actual_datetime",
			"original_outcome",
			"original_administered_dose",
			"original_dose_unit",
			"created_by",
			"created_on",
			"reviewed_by",
			"reviewed_on",
		].forEach((fieldname) => frm.set_df_property(fieldname, "read_only", 1));
	},
});
