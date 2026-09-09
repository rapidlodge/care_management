frappe.ui.form.on("Incident", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.incident.incident.search_incident_participants",
		}));
	},
});
