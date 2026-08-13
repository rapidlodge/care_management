frappe.views.calendar["Medication Administration Log"] = {
	field_map: {
		"start": "date",
		"end": "date",
		"id": "name",
		"title": "medication_task",
		"allDay": "allDay"
	},
	style_map: {
		"Public": "danger",
		"Private": "info"
	},
	get_events_method: "frappe.desk.calendar.get_events"
};
